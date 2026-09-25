from django.contrib import admin
from .models import Booking, ChatMessage, ChatSession, Diagnosis, MediaUpload

admin.site.register(ChatSession)
admin.site.register(ChatMessage)
admin.site.register(MediaUpload)
admin.site.register(Diagnosis)
admin.site.register(Booking)
