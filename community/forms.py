from django import forms
from .models import ContentReport, Question, Reply


class QuestionForm(forms.ModelForm):
    body = forms.CharField(
        max_length=5000,
        widget=forms.Textarea(attrs={
            'rows': 6,
            'placeholder': 'Add any context that will help the community respond.',
        }),
    )

    class Meta:
        model = Question
        fields = ['title', 'body', 'is_anonymous']
        widgets = {
            'title': forms.TextInput(attrs={'maxlength': 180, 'placeholder': 'What would you like to ask?'}),
            'is_anonymous': forms.CheckboxInput(),
        }
        labels = {
            'body': 'Question details',
            'is_anonymous': 'Post anonymously',
        }


class ReplyForm(forms.ModelForm):
    body = forms.CharField(
        max_length=5000,
        widget=forms.Textarea(attrs={'rows': 4, 'placeholder': 'Write a helpful reply...'}),
    )
    parent_id = forms.IntegerField(required=False, widget=forms.HiddenInput())

    class Meta:
        model = Reply
        fields = ['body', 'is_anonymous']
        widgets = {
            'is_anonymous': forms.CheckboxInput(),
        }
        labels = {
            'body': 'Your reply',
            'is_anonymous': 'Reply anonymously',
        }


class ReportForm(forms.ModelForm):
    class Meta:
        model = ContentReport
        fields = ['reason']
        widgets = {
            'reason': forms.Textarea(attrs={
                'rows': 2,
                'maxlength': 500,
                'placeholder': 'Tell moderators why this should be reviewed.',
            }),
        }
        labels = {'reason': 'Reason for report'}
