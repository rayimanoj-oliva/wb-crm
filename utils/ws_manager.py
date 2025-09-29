from typing import List

from fastapi import FastAPI, WebSocket,WebSocketDisconnect

class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        try:
            print(f"[WS] Connected. Active connections: {len(self.active_connections)}")
        except Exception:
            pass

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)
        try:
            print(f"[WS] Disconnected. Active connections: {len(self.active_connections)}")
        except Exception:
            pass

    async def broadcast(self, message: dict):
        disconnected = []
        try:
            print(f"[WS] Broadcasting to {len(self.active_connections)} connections. Payload keys: {list(message.keys())}")
        except Exception:
            pass
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except WebSocketDisconnect:
                disconnected.append(connection)
            except Exception as e:
                try:
                    print(f"[WS] Broadcast error: {e}")
                except Exception:
                    pass
        for conn in disconnected:
            self.disconnect(conn)

manager = ConnectionManager()