from fastapi import APIRouter, WebSocket, WebSocketDisconnect
import asyncio
from utils.ws_manager import manager

router = APIRouter()

@router.websocket("/channel")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            try:
                _ = await websocket.receive_text()
            except WebSocketDisconnect:
                break
            except RuntimeError:
                break
            except Exception:
                await asyncio.sleep(0.5)
    except WebSocketDisconnect:
        pass
    finally:
        manager.disconnect(websocket)
