"""Solo permite leer el canal SSE propio: user-<id>."""
from django_eventstream.channelmanager import DefaultChannelManager


class PanelWebChannelManager(DefaultChannelManager):
    def get_channels_for_request(self, request, view_kwargs):
        channels = super().get_channels_for_request(request, view_kwargs)
        if not channels and getattr(request, 'user', None) and request.user.is_authenticated:
            return {f'user-{request.user.id}'}
        return channels

    def can_read_channel(self, user, channel):
        if user is None or not getattr(user, 'is_authenticated', False):
            return False
        if not user.is_authenticated:
            return False
        return channel == f'user-{user.pk}'
