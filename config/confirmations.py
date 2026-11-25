from django.shortcuts import render


def render_confirmation(request, *, title, message, confirm_label, cancel_url, hidden_fields=None):
    return render(request, 'confirm_action.html', {
        'confirmation_title': title,
        'confirmation_message': message,
        'confirmation_label': confirm_label,
        'cancel_url': cancel_url,
        'hidden_fields': hidden_fields or {},
    })
