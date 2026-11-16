from django import forms
from .models import Lesson
from pods.models import Pod


class LessonForm(forms.ModelForm):
    """
    Form for uploading and creating new lessons.
    """
    ALLOWED_MIME_TYPES = {'audio/mpeg', 'audio/mp3', 'audio/wav', 'application/pdf'}
    MAX_FILE_SIZE = 10 * 1024 * 1024

    class Meta:
        model = Lesson
        fields = ['title', 'description', 'content', 'audio_file', 'pdf_resource', 'is_master_template']
        widgets = {
            'title': forms.TextInput(attrs={'class': 'w-full p-2.5 border rounded-lg', 'placeholder': 'Lesson Title'}),
            'description': forms.Textarea(attrs={'class': 'w-full p-2.5 border rounded-lg', 'rows': 2, 'placeholder': 'Brief summary...'}),
            'content': forms.Textarea(attrs={'class': 'w-full p-2.5 border rounded-lg', 'rows': 8, 'placeholder': 'Full teaching content, scriptures, and discussion questions...'}),
            'is_master_template': forms.CheckboxInput(attrs={'class': 'w-4 h-4 text-indigo-600 rounded'}),
        }

    def clean_audio_file(self):
        audio_file = self.cleaned_data.get('audio_file')
        if not audio_file:
            return audio_file
        if audio_file.size > self.MAX_FILE_SIZE:
            raise forms.ValidationError('Audio file must be 10MB or smaller.')
        if audio_file.content_type not in self.ALLOWED_MIME_TYPES and not audio_file.name.lower().endswith(('.mp3', '.wav', '.m4a')):
            raise forms.ValidationError('Only audio files (.mp3, .wav, .m4a) are allowed.')
        return audio_file

    def clean_pdf_resource(self):
        pdf_resource = self.cleaned_data.get('pdf_resource')
        if not pdf_resource:
            return pdf_resource
        if pdf_resource.size > self.MAX_FILE_SIZE:
            raise forms.ValidationError('PDF resource must be 10MB or smaller.')
        if pdf_resource.content_type != 'application/pdf' and not pdf_resource.name.lower().endswith('.pdf'):
            raise forms.ValidationError('Only PDF files are allowed for the resource.')
        return pdf_resource


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
