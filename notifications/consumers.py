import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async

class NotificationConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.user = self.scope["user"]
        
        # 🛡️ Security Check: Ensure only authenticated users can connect
        if not self.user.is_authenticated:
            await self.close()
            return
            
        # Create a unique personal room for the user
        self.room_group_name = f"notifications_user_{self.user.id}"

        # Join the personal room group
        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )

        await self.accept()

    async def disconnect(self, close_code):
        # Leave the group on disconnect
        if hasattr(self, 'room_group_name'):
            await self.channel_layer.group_discard(
                self.room_group_name,
                self.channel_name
            )

    async def receive(self, text_data):
        # We don't expect client-to-server messages for notifications,
        # but we can handle them if required for "Mark as Read" actions.
        pass

    # 📡 Custom Event Handler for 'send_notification'
    async def send_notification(self, event):
        """
        Receives notification data from the channel layer and pushes to WebSocket.
        """
        payload = event.get('payload', {})
        
        # Send JSON payload directly to the frontend
        await self.send(text_data=json.dumps(payload))
