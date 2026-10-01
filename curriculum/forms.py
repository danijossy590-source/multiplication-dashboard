from django import forms
from .models import Lesson
from pods.models import Pod

class LessonForm(forms.ModelForm):
    """
    Form for uploading and creating new lessons.
    """
    class Meta:
        model = Lesson
        fields = ['title', 'description', 'content', 'audio_file', 'pdf_resource', 'is_master_template']
        widgets = {
            'title': forms.TextInput(attrs={'class': 'w-full p-2.5 border rounded-lg', 'placeholder': 'Lesson Title'}),
            'description': forms.Textarea(attrs={'class': 'w-full p-2.5 border rounded-lg', 'rows': 2, 'placeholder': 'Brief summary...'}),
            'content': forms.Textarea(attrs={'class': 'w-full p-2.5 border rounded-lg', 'rows': 8, 'placeholder': 'Full teaching content, scriptures, and discussion questions...'}),
            'is_master_template': forms.CheckboxInput(attrs={'class': 'w-4 h-4 text-indigo-600 rounded'}),
        }


class TeachThisForm(forms.Form):
    """
    Form allowing a user to select a Pod they lead to receive the cloned lesson.
    """
    target_pod = forms.ModelChoiceField(
        queryset=Pod.objects.none(),
        widget=forms.Select(attrs={'class': 'w-full p-2.5 border rounded-lg'}),
        help_text="Select the Pod where you want to teach this lesson."
    )

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        if user:
            self.fields['target_pod'].queryset = Pod.objects.filter(leader=user)
