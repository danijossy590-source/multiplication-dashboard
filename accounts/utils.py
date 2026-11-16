from django.contrib.auth import get_user_model
from pods.models import Pod
from growth.models import Reflection
from .models import Mentorship, Notification

User = get_user_model()


def notify_user(user, title, message, related_url=''):
    if not user or not getattr(user, 'is_authenticated', False):
        return None
    return Notification.objects.create(
        user=user,
        title=title,
        message=message,
        related_url=related_url,
    )


def build_discipleship_tree(user, depth=1, max_depth=5):
    """
    Recursively builds a tree structure of spiritual progeny up to max_depth.
    Returns a dictionary structure suitable for visual rendering.
    """
    if not user or not getattr(user, 'is_authenticated', False):
        return []
    if depth > max_depth:
        return []

    direct_mentees = User.objects.filter(mentorship_mentees__mentor=user).distinct()

    tree_nodes = []
    for mentee in direct_mentees:
        children = build_discipleship_tree(mentee, depth + 1, max_depth)

        completed_challenges = Reflection.objects.filter(user=mentee, is_approved=True).count()
        led_pods_count = Pod.objects.filter(leader=mentee).count()

        total_progeny = len(children) + sum(child.get('total_progeny', 0) for child in children)
        node = {
            'id': mentee.id,
            'name': mentee.get_full_name() or mentee.username,
            'email': mentee.email,
            'generation': depth,
            'completed_challenges': completed_challenges,
            'is_leader': led_pods_count > 0,
            'children': children,
            'total_progeny': total_progeny,
        }
        tree_nodes.append(node)

    return tree_nodes


def get_multiplication_stats(user):
    """
    Computes top-level dashboard metrics for a leader.
    """
    if not user or not getattr(user, 'is_authenticated', False):
        return {
            'total_footprint': 0,
            'gen_1_count': 0,
            'gen_2_plus_count': 0,
            'max_depth': 0,
            'tree': [],
        }

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
        'tree': tree,
    }


def get_discipleship_tree_cte(leader_id):
    """
    Compatibility helper for callers expecting a tree structure from a leader.
    """
    try:
        leader = User.objects.get(pk=leader_id)
    except User.DoesNotExist:
        return []
    return build_discipleship_tree(leader)