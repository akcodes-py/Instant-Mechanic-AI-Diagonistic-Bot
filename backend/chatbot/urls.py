from django.urls import path
from .views import (
    booking_detail,
    booking_view,
    chat_view,
    conversation_history,
    diagnosis_view,
    upload_view,
)

urlpatterns = [
    path("chat/", chat_view, name="chat"),
    path("upload/", upload_view, name="upload"),
    path("diagnosis/", diagnosis_view, name="diagnosis"),
    path("booking/", booking_view, name="booking-create"),
    path("booking/<uuid:id>/", booking_detail, name="booking-detail"),
    path("history/<uuid:session_id>/", conversation_history, name="history"),
]
