import os
import sys
import traceback

# Force UTF-8 encoding for standard output to avoid GBK print errors on Windows
if sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Optional
import asyncio
import json

# Import core modules
# NOTE: Make sure the BinanceConfig in account_info and order_manager is correctly set up.
try:
    from core.account_info import AccountSnapshot, AccountFunds, PositionInfo
    from core.order_manager import OrderManager, LeverageManager
    from core.live_engine import live_engine
except ImportError as e:
    print(f"Warning: Failed to import core modules. Error: {e}")

app = FastAPI(title="Nexus Quant API")

# --- Pydantic Models for API Requests ---
class LeverageRequest(BaseModel):
    symbol: str
    leverage: int

class MarketOrderRequest(BaseModel):
    symbol: str
    side: str          # BUY / SELL
    position_side: str # LONG / SHORT
    quantity: float

class CancelPanicRequest(BaseModel):
    symbol: str

class UpdateKeysRequest(BaseModel):
    api_key: str
    secret_key: str

# --- API Routes ---

@app.post("/api/config/keys")
def update_api_keys(req: UpdateKeysRequest):
    try:
        from core.account_info import BinanceConfig as AccConfig
        from core.order_manager import BinanceConfig as OMConfig
        AccConfig.API_KEY = req.api_key
        AccConfig.SECRET_KEY = req.secret_key
        OMConfig.API_KEY = req.api_key
        OMConfig.SECRET_KEY = req.secret_key
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/account/snapshot")
def get_account_snapshot():
    try:
        # Calls the actual AccountSnapshot logic
        # For safety in the demo, we wrap in try-except in case API keys are not set
        res = AccountSnapshot.full_snapshot()
        return {"status": "success", "data": res}
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/trade/leverage")
def set_leverage(req: LeverageRequest):
    try:
        res = LeverageManager.set_leverage(leverage=req.leverage, symbol=req.symbol)
        return {"status": "success", "data": res}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/trade/market")
def place_market_order(req: MarketOrderRequest):
    try:
        # Map parameters to the specific methods in OrderManager
        if req.side == "BUY" and req.position_side == "LONG":
            res = OrderManager.market_open_long(req.quantity, symbol=req.symbol)
        elif req.side == "SELL" and req.position_side == "LONG":
            res = OrderManager.market_close_long(req.quantity, symbol=req.symbol)
        elif req.side == "SELL" and req.position_side == "SHORT":
            res = OrderManager.market_open_short(req.quantity, symbol=req.symbol)
        elif req.side == "BUY" and req.position_side == "SHORT":
            res = OrderManager.market_close_short(req.quantity, symbol=req.symbol)
        else:
            raise ValueError("Invalid side/position_side combination")
        
        return {"status": "success", "data": res}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/trade/panic")
def panic_close_all(req: CancelPanicRequest):
    try:
        symbol = req.symbol
        # 1. Cancel all open orders
        OrderManager.cancel_all_open_orders(symbol=symbol)
        
        # 2. Get current positions and market close them
        positions = OrderManager.get_position(symbol=symbol)
        closed_orders = []
        for p in positions:
            amt = float(p.get("positionAmt", 0))
            if amt > 0:
                res = OrderManager.market_close_long(abs(amt), symbol=symbol)
                closed_orders.append(res)
            elif amt < 0:
                res = OrderManager.market_close_short(abs(amt), symbol=symbol)
                closed_orders.append(res)
                
        return {
            "status": "success", 
            "message": "Panic protocol executed",
            "closed_positions": closed_orders
        }
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

# --- WebSocket Route for Live Engine ---
from fastapi import WebSocket, WebSocketDisconnect

@app.websocket("/api/ws/bot")
async def websocket_bot_endpoint(websocket: WebSocket):
    await websocket.accept()
    queue = asyncio.Queue()
    await live_engine.add_client(queue)
    
    # Task to read messages from the client (START/STOP commands)
    async def receive_from_client():
        try:
            while True:
                data = await websocket.receive_text()
                payload = json.loads(data)
                action = payload.get("action")
                if action == "start":
                    symbol = payload.get("symbol", "ETHUSDC")
                    live_engine.start(symbol)
                elif action == "stop":
                    live_engine.stop()
        except WebSocketDisconnect:
            pass
        except Exception as e:
            print("WS Receive Error:", e)

    # Task to send messages from LiveEngine to the client
    async def send_to_client():
        try:
            while True:
                msg = await queue.get()
                await websocket.send_text(json.dumps(msg))
        except WebSocketDisconnect:
            pass
        except Exception as e:
            print("WS Send Error:", e)

    task_recv = asyncio.create_task(receive_from_client())
    task_send = asyncio.create_task(send_to_client())
    
    try:
        await asyncio.gather(task_recv, task_send)
    finally:
        task_recv.cancel()
        task_send.cancel()
        await live_engine.remove_client(queue)

# --- Serve Frontend Static Files ---
frontend_dir = os.path.join(os.path.dirname(__file__), "frontend")
app.mount("/assets", StaticFiles(directory=frontend_dir), name="assets")

@app.get("/")
def read_index():
    return FileResponse(os.path.join(frontend_dir, "index.html"))

@app.get("/{filename}")
def serve_file(filename: str):
    file_path = os.path.join(frontend_dir, filename)
    if os.path.exists(file_path):
        return FileResponse(file_path)
    raise HTTPException(status_code=404, detail="File not found")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
