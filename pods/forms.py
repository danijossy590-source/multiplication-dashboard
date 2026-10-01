from django import forms
from django.contrib.auth import get_user_model
from .models import Pod, PodMember

User = get_user_model()


class PodForm(forms.ModelForm):
    '''this creates the Pod form'''
    class Meta:
        model = Pod
        fields = ['name', 'description']

class AddMemberForm(forms.ModelForm):
    """Form to add an existing registered user to a Pod. """
    username = forms.CharField(
        max_length=150,
        widget=forms.TextInput(attrs={'class': 'w-full p-2 border rounded', 'placeholder': 'Enter Disciple username'})
    )
    

    role = forms.ChoiceField(
        choices=PodMember.ROLE_CHOICES,
        widget=forms.Select(attrs={'class': 'w-full p-2 border rounded'})
    )


class LaunchApprenticePodForm(forms.Form):
    """
    Form used by a Mentor to deploy an Apprentice to lead a new branch Pod.
    """
    apprentice = forms.ModelChoiceField(
        queryset=User.objects.none(),
        widget=forms.Select(attrs={'class': 'w-full p-2 border rounded'}),
        help_text="Select a disciple to appoint as Apprentice Leader"
    )
    new_pod_name = forms.CharField(
        max_length=150,
        widget=forms.TextInput(attrs={'class': 'w-full p-2 border rounded', 'placeholder': 'Name for the Apprentice\'s Pod'})
    )
    new_pod_description = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={'class': 'w-full p-2 border rounded', 'rows': 2, 'placeholder': 'Description for new Pod'})
    )

    def __init__(self, *args, **kwargs):
        leader = kwargs.pop('leader', None)
        super().__init__(*args, **kwargs)
        if leader:
            # Only allow selecting members from pods led by this leader
            pod_ids = Pod.objects.filter(leader=leader).values_list('id', flat=True)
            member_user_ids = PodMember.objects.filter(pod_id__in=pod_ids).values_list('user_id', flat=True)
            self.fields['apprentice'].queryset = User.objects.filter(id__in=member_user_ids).exclude(id=leader.id)
