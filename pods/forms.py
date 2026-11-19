from django import forms
from django.contrib.auth import get_user_model
from .models import Pod, PodMember

User = get_user_model()


class PodForm(forms.ModelForm):
    '''this creates the Pod form'''
    class Meta:
        model = Pod
        fields = ['name', 'description']

    def __init__(self, *args, **kwargs):
        is_admin = kwargs.pop('is_admin', False)
        super().__init__(*args, **kwargs)
        if is_admin:
            active_users = User.objects.filter(is_active=True).order_by('username')
            self.fields['leader'] = forms.ModelChoiceField(
                queryset=active_users,
                help_text="Choose the primary leader for this Pod.",
            )
            self.fields['mentors'] = forms.ModelMultipleChoiceField(
                queryset=active_users,
                required=False,
                widget=forms.CheckboxSelectMultiple,
                help_text="Optionally assign mentors who can participate in this Pod.",
            )


class AddMemberForm(forms.Form):
    """Form to add an existing registered user to a Pod. """
    username = forms.CharField(
        max_length=150,
        widget=forms.TextInput(attrs={'class': 'w-full p-2 border rounded', 'placeholder': 'Enter Disciple username'})
    )
    

    role = forms.ChoiceField(
        choices=[choice for choice in PodMember.ROLE_CHOICES if choice[0] != 'LEADER'],
        widget=forms.Select(attrs={'class': 'w-full p-2 border rounded'})
    )


class JoinPodForm(forms.Form):
    code = forms.CharField(
        max_length=24,
        strip=True,
        widget=forms.TextInput(attrs={
            'autocomplete': 'off',
            'placeholder': 'Enter the Pod access code',
            'class': 'w-full rounded-lg border p-2.5',
        }),
    )


class AssignMentorsForm(forms.Form):
    mentors = forms.ModelMultipleChoiceField(
        queryset=User.objects.none(),
        required=False,
        widget=forms.CheckboxSelectMultiple,
        help_text="Selected mentors can view and participate in this Pod.",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['mentors'].queryset = User.objects.filter(is_active=True).order_by('username')


class PodMessageForm(forms.Form):
    body = forms.CharField(
        max_length=2000,
        widget=forms.Textarea(attrs={
            'class': 'w-full p-3 border rounded-lg',
            'rows': 2,
            'placeholder': 'Write a message to your Pod...',
        }),
    )


class PodMeetingForm(forms.Form):
    title = forms.CharField(max_length=150)
    details = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={'rows': 2}),
    )
    scheduled_at = forms.DateTimeField(
        label="Date and time (UTC)",
        input_formats=['%Y-%m-%dT%H:%M'],
        widget=forms.DateTimeInput(attrs={'type': 'datetime-local'}),
    )
    meeting_url = forms.URLField(required=False)


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
