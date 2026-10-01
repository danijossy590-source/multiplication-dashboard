from django.contrib.auth import get_user_model
from pods.models import Pod
from growth.models import Reflection

User = get_user_model()

def build_discipleship_tree(user, depth=1, max_depth=5):
    """
    Recursively builds a tree structure of spiritual progeny up to max_depth.
    Returns a dictionary structure suitable for visual rendering.
    """
    if depth > max_depth:
        return []

    # Retrieve mentees where this user is assigned as mentor/leader
    # Assumes a Mentorship model or direct mentor field in User/Pod
    direct_mentees = User.objects.filter(mentorships_as_mentee__mentor=user, mentorships_as_mentee__is_active=True).distinct()

    tree_nodes = []
    for mentee in direct_mentees:
        children = build_discipleship_tree(mentee, depth + 1, max_depth)
        
        # Calculate individual stats
        completed_challenges = Reflection.objects.filter(user=mentee, is_approved=True).count()
        led_pods_count = Pod.objects.filter(leader=mentee).count()

        node = {
            'id': mentee.id,
            'name': mentee.get_full_name() or mentee.username,
            'email': mentee.email,
            'generation': depth,
            'completed_challenges': completed_challenges,
            'is_leader': led_pods_count > 0,
            'children': children,
            'total_progeny': len(children) + sum(c['total_progeny'] for c in children)
        }
        tree_nodes.append(node)

    return tree_nodes


def get_multiplication_stats(user):
    """
    Computes top-level dashboard metrics for a leader.
    """
    tree = build_discipleship_tree(user)
    
    def count_by_generation(nodes, current_gen=1, stats_dict=None):
        if stats_dict is None:
            stats_dict = {}
        for node in nodes:
            stats_dict[current_gen] = stats_dict.get(current_gen, 0) + 1
            count_by_generation(node['children'], current_gen + 1, stats_dict)
        return stats_dict

    gen_counts = count_by_generation(tree)
    total_footprint = sum(gen_counts.values())
    max_gen_depth = max(gen_counts.keys()) if gen_counts else 0

    return {
        'total_footprint': total_footprint,
        'gen_1_count': gen_counts.get(1, 0),
        'gen_2_plus_count': total_footprint - gen_counts.get(1, 0),
        'max_depth': max_gen_depth,
        'tree': tree
    }
from django.db import connection

def get_discipleship_tree_cte(leader_id):
    """
    Fetches all multi-generational descendants in 1 single database round-trip
    using PostgreSQL Recursive CTEs.
    """
    query = """
    WITH RECURSIVE discipleship_cte AS (
        -- Base Case: Direct (Gen 1) Mentees
        SELECT 
            mentee_id, mentor_id, 1 AS generation
        FROM pods_mentorship
        WHERE mentor_id = %s AND is_active = TRUE

        UNION ALL

        -- Recursive Case: Sub-generations (Gen 2, Gen 3, etc.)
        SELECT 
            m.mentee_id, m.mentor_id, c.generation + 1
        FROM pods_mentorship m
        INNER JOIN discipleship_cte c ON m.mentor_id = c.mentee_id
        WHERE m.is_active = TRUE
    )
    SELECT * FROM discipleship_cte;
    """
    with connection.cursor() as cursor:
        cursor.execute(query, [leader_id])
        rows = cursor.fetchall()
        
    return rows