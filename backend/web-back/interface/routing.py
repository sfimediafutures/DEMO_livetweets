from django.urls import path

from . import consumers

websocket_urlpatterns = [
    path(r'ws/tweets', consumers.TweetConsumer.as_asgi()),
]
