from django import forms
from .models import Assignment, Reflection

class AssignmentForm(forms.ModelForm):
    """
    Form for leaders to issue practical challenges to their disciples.
    """
    class Meta:
        model = Assignment
        fields = ['title', 'lesson', 'pod', 'instruction', 'due_date']
        widgets = {
            'title': forms.TextInput(attrs={'class': 'w-full p-2.5 border rounded-lg focus:ring-2 focus:ring-indigo-500', 'placeholder': 'e.g., Pray for 3 Non-Believers This Week'}),
            'lesson': forms.Select(attrs={'class': 'w-full p-2.5 border rounded-lg'}),
            'pod': forms.Select(attrs={'class': 'w-full p-2.5 border rounded-lg'}),
            'instruction': forms.Textarea(attrs={'class': 'w-full p-2.5 border rounded-lg', 'rows': 4, 'placeholder': 'Describe the specific action steps...'}),
            'due_date': forms.DateInput(attrs={'class': 'w-full p-2.5 border rounded-lg', 'type': 'date'}),
        }


class ReflectionForm(forms.ModelForm):
    """
    Form for disciples to submit written text and upload audio files.
    """
    class Meta:
        model = Reflection
        fields = ['written_content', 'audio_reflection']
        widgets = {
            'written_content': forms.Textarea(attrs={
                'class': 'w-full p-3 border rounded-xl focus:ring-2 focus:ring-indigo-500',
                'rows': 5,
                'placeholder': 'Reflect on your experience completing this assignment...'
            }),
            'audio_reflection': forms.FileInput(attrs={
                'class': 'w-full text-sm text-slate-500 file:mr-4 file:py-2 file:px-4 file:rounded-lg file:border-0 file:text-sm file:font-semibold file:bg-indigo-50 file:text-indigo-700 hover:file:bg-indigo-100 cursor-pointer',
                'accept': 'audio/*'
            }),
        }


class MentorFeedbackForm(forms.ModelForm):
    """
    Form for mentors to leave feedback and approve submissions.
    """
    class Meta:
        model = Reflection
        fields = ['mentor_feedback', 'is_approved']
        widgets = {
            'mentor_feedback': forms.Textarea(attrs={
                'class': 'w-full p-3 border rounded-xl focus:ring-2 focus:ring-indigo-500',
                'rows': 4,
                'placeholder': 'Encourage your disciple and provide helpful direction...'
            }),
            'is_approved': forms.CheckboxInput(attrs={
                'class': 'w-5 h-5 text-indigo-600 rounded focus:ring-indigo-500 border-gray-300'
            }),
        }