from django import forms
from django.contrib.auth.forms import UserCreationForm, UserChangeForm
from .models import CustomUser

class CustomUserCreationForm(UserCreationForm):
    email = forms.EmailField(
        required=True,
        help_text='Used for password recovery.',
    )

    class Meta:
        model = CustomUser
        fields = ('username', 'email', 'phone_number', 'bio')

    def save(self, commit=True):
        user = super().save(commit=False)
        user.role = 'mentee'
        if commit:
            user.save()
            self.save_m2m()
        return user


class AdminUserCreationForm(UserCreationForm):
    class Meta(UserCreationForm.Meta):
        model = CustomUser
        fields = ('username', 'email', 'role', 'phone_number', 'bio')


class CustomUserChangeForm(UserChangeForm):
    class Meta:
        model = CustomUser
        fields = '__all__'

    def clean(self):
        cleaned_data = super().clean()
        if cleaned_data.get('role') != 'admin':
            cleaned_data['is_staff'] = False
            cleaned_data['is_superuser'] = False
        return cleaned_data


class ProfileForm(forms.ModelForm):
    class Meta:
        model = CustomUser
        fields = ('first_name', 'last_name', 'email', 'phone_number', 'bio')
        widgets = {
            'first_name': forms.TextInput(attrs={'autocomplete': 'given-name'}),
            'last_name': forms.TextInput(attrs={'autocomplete': 'family-name'}),
            'email': forms.EmailInput(attrs={'autocomplete': 'email'}),
            'phone_number': forms.TextInput(attrs={'autocomplete': 'tel'}),
            'bio': forms.Textarea(attrs={'rows': 5, 'maxlength': 500}),
        }