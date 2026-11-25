from django import forms
from django.core.exceptions import ValidationError
from django.db.models import Q
from .models import Course, Lesson, Module, ModuleQuiz
from pods.models import Pod


class LessonForm(forms.ModelForm):
    """
    Form for uploading and creating new lessons.
    """
    ALLOWED_MIME_TYPES = {'audio/mpeg', 'audio/mp3', 'audio/wav', 'application/pdf'}
    MAX_FILE_SIZE = 10 * 1024 * 1024
    word_document = forms.FileField(
        required=False,
        label='Word lesson document',
        help_text='Upload a .doc or .docx file. Its text will fill the lesson content and it will be converted to a PDF resource.',
    )

    class Meta:
        model = Lesson
        fields = [
            'title',
            'description',
            'content',
            'discussion_questions',
            'audio_file',
            'pdf_resource',
            'is_master_template',
        ]
        widgets = {
            'title': forms.TextInput(attrs={'class': 'w-full p-2.5 border rounded-lg', 'placeholder': 'Lesson Title'}),
            'description': forms.Textarea(attrs={'class': 'w-full p-2.5 border rounded-lg', 'rows': 2, 'placeholder': 'Brief summary...'}),
            'content': forms.Textarea(attrs={'class': 'w-full p-2.5 border rounded-lg', 'rows': 8, 'placeholder': 'Full teaching content, scriptures, and discussion questions...'}),
            'discussion_questions': forms.Textarea(attrs={'class': 'w-full p-2.5 border rounded-lg', 'rows': 4, 'placeholder': 'Optional editor-reviewed discussion questions...'}),
            'is_master_template': forms.CheckboxInput(attrs={'class': 'w-4 h-4 text-indigo-600 rounded'}),
        }

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        self.fields['content'].required = False
        self.fields['module'] = forms.ModelChoiceField(
            queryset=Module.objects.none(),
            required=False,
            help_text='Optionally place this lesson in a course module.',
        )
        self.fields['order'] = forms.IntegerField(min_value=0, required=False, initial=0)
        if user:
            modules = Module.objects.select_related('course')
            if not (user.is_staff or user.is_superuser):
                modules = modules.filter(
                    Q(course__pod__leader=user)
                    | Q(course__pod__isnull=True, course__created_by=user)
                )
            if self.instance.pk and self.instance.module_id:
                modules = modules | Module.objects.filter(pk=self.instance.module_id)
            self.fields['module'].queryset = modules.order_by('course__title', 'order')

    def clean_audio_file(self):
        audio_file = self.cleaned_data.get('audio_file')
        if not audio_file or not self.files.get(self.add_prefix('audio_file')):
            return audio_file
        if audio_file.size > self.MAX_FILE_SIZE:
            raise forms.ValidationError('Audio file must be 10MB or smaller.')
        if audio_file.content_type not in self.ALLOWED_MIME_TYPES and not audio_file.name.lower().endswith(('.mp3', '.wav', '.m4a')):
            raise forms.ValidationError('Only audio files (.mp3, .wav, .m4a) are allowed.')
        return audio_file

    def clean_pdf_resource(self):
        pdf_resource = self.cleaned_data.get('pdf_resource')
        if not pdf_resource or not self.files.get(self.add_prefix('pdf_resource')):
            return pdf_resource
        if pdf_resource.size > self.MAX_FILE_SIZE:
            raise forms.ValidationError('PDF resource must be 10MB or smaller.')
        if pdf_resource.content_type != 'application/pdf' and not pdf_resource.name.lower().endswith('.pdf'):
            raise forms.ValidationError('Only PDF files are allowed for the resource.')
        return pdf_resource

    def clean_word_document(self):
        word_document = self.cleaned_data.get('word_document')
        if not word_document:
            return word_document
        if word_document.size > self.MAX_FILE_SIZE:
            raise forms.ValidationError('Word document must be 10MB or smaller.')
        if not word_document.name.lower().endswith(('.doc', '.docx')):
            raise forms.ValidationError('Only Word documents (.doc or .docx) are supported.')
        return word_document

    def clean(self):
        cleaned_data = super().clean()
        word_document = cleaned_data.get('word_document')
        content = cleaned_data.get('content')

        if word_document and self.files.get(self.add_prefix('pdf_resource')):
            self.add_error('pdf_resource', 'Upload either a Word lesson document or a PDF resource, not both.')
        if not word_document and not content:
            self.add_error('content', 'Enter lesson content or upload a Word lesson document.')
        return cleaned_data


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


class CourseForm(forms.ModelForm):
    class Meta:
        model = Course
        fields = ['title', 'description', 'pod', 'order', 'is_published']

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user')
        super().__init__(*args, **kwargs)
        if user.is_staff or user.is_superuser:
            self.fields['pod'].queryset = Pod.objects.order_by('name')
        else:
            self.fields['pod'].queryset = Pod.objects.filter(leader=user).order_by('name')
            self.fields['pod'].required = True
            self.fields['pod'].help_text = 'Choose one of the Pods you lead.'
            if self.instance.pk and self.instance.pod_id is None:
                self.fields['pod'].required = False
                self.fields['pod'].help_text = 'Leave blank to keep this course available to all learners.'


class CourseGenerationForm(forms.Form):
    MAX_LESSONS = 24
    MAX_SOURCE_CHARACTERS = 20000

    title = forms.CharField(
        max_length=200,
        label='Course title',
        widget=forms.TextInput(attrs={
            'class': 'w-full rounded-lg border border-gray-300 p-2.5',
            'placeholder': 'e.g., Foundations of Discipleship',
        }),
    )
    pod = forms.ModelChoiceField(
        queryset=Pod.objects.none(),
        required=False,
        empty_label='Global course',
        help_text='Choose a Pod for a Pod-specific course, or leave blank for a global course.',
    )
    lessons = forms.ModelMultipleChoiceField(
        queryset=Lesson.objects.none(),
        widget=forms.CheckboxSelectMultiple,
        help_text='Select up to 24 unassigned lessons. Their content will be sent to the configured AI provider for analysis.',
    )

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user')
        super().__init__(*args, **kwargs)
        is_admin = user.is_staff or user.is_superuser
        if is_admin:
            self.fields['pod'].queryset = Pod.objects.order_by('name')
            lessons = Lesson.objects.filter(module__isnull=True)
        else:
            self.fields['pod'].queryset = Pod.objects.filter(leader=user).order_by('name')
            self.fields['pod'].required = True
            self.fields['pod'].empty_label = None
            lessons = Lesson.objects.filter(module__isnull=True).filter(
                Q(created_by=user)
                | Q(pod__leader=user)
                | Q(is_master_template=True)
            )
        self.fields['lessons'].queryset = lessons.select_related('pod', 'created_by').order_by(
            'title',
            'id',
        ).distinct()
        self.user = user
        self.is_admin = is_admin

    def clean(self):
        cleaned_data = super().clean()
        pod = cleaned_data.get('pod')
        lessons = cleaned_data.get('lessons')
        if not lessons:
            return cleaned_data

        selected_lessons = list(lessons)
        if len(selected_lessons) > self.MAX_LESSONS:
            self.add_error('lessons', f'Select no more than {self.MAX_LESSONS} lessons at a time.')
            return cleaned_data

        source_length = sum(len(lesson.content) for lesson in selected_lessons)
        if source_length > self.MAX_SOURCE_CHARACTERS:
            self.add_error(
                'lessons',
                'The selected lesson content is too large for one course analysis. Select fewer or shorter lessons.',
            )

        if pod:
            mismatched_pods = [
                lesson for lesson in selected_lessons
                if lesson.pod_id and lesson.pod_id != pod.pk
            ]
            if mismatched_pods:
                self.add_error('lessons', 'Select lessons from the chosen Pod or global lessons.')
        elif any(lesson.pod_id for lesson in selected_lessons):
            self.add_error('pod', 'Choose the Pod that owns the selected lessons.')

        return cleaned_data


class ModuleForm(forms.ModelForm):
    class Meta:
        model = Module
        fields = ['title', 'description', 'order']


class QuizSettingsForm(forms.ModelForm):
    class Meta:
        model = ModuleQuiz
        fields = ['title', 'passing_score']
        widgets = {
            'passing_score': forms.NumberInput(attrs={'min': 1, 'max': 100}),
        }

    def clean_passing_score(self):
        score = self.cleaned_data['passing_score']
        if not 1 <= score <= 100:
            raise ValidationError('Passing score must be between 1 and 100.')
        return score


class QuizQuestionForm(forms.Form):
    prompt = forms.CharField(widget=forms.Textarea(attrs={'rows': 2}))
    choice_1 = forms.CharField(max_length=500, label='Answer 1')
    choice_2 = forms.CharField(max_length=500, label='Answer 2')
    choice_3 = forms.CharField(max_length=500, label='Answer 3')
    choice_4 = forms.CharField(max_length=500, label='Answer 4')
    correct_choice = forms.ChoiceField(
        choices=[('1', 'Answer 1'), ('2', 'Answer 2'), ('3', 'Answer 3'), ('4', 'Answer 4')],
        widget=forms.RadioSelect,
    )
