from fastapi import APIRouter, WebSocket, WebSocketDisconnect
import asyncio
import logging

router = APIRouter(prefix="/api/relay", tags=["Relay"])
logger = logging.getLogger(__name__)

class AgentConnection:
    def __init__(self, ws: WebSocket):
        self.ws = ws
        self.hub_queue = asyncio.Queue()

# 全局内存字典，用于存储当前存活的 agent 连接
active_agents: dict[str, AgentConnection] = {}

@router.websocket("/agent/{agent_id}")
async def agent_endpoint(websocket: WebSocket, agent_id: str):
    """Local Bridge 客户端连接至此端点，等待 Playwright 后端指令。"""
    await websocket.accept()
    conn = AgentConnection(websocket)
    active_agents[agent_id] = conn
    logger.info(f"Agent connected: {agent_id}")
    try:
        while True:
            # 统一由 agent_endpoint 接收数据，避免 concurrent receive() error
            data = await websocket.receive_text()
            await conn.hub_queue.put(data)
    except WebSocketDisconnect:
        logger.info(f"Agent disconnected: {agent_id}")
    finally:
        if active_agents.get(agent_id) == conn:
            active_agents.pop(agent_id, None)


@router.websocket("/hub/{agent_id}")
async def hub_endpoint(websocket: WebSocket, agent_id: str):
    """Playwright (p.chromium.connect_over_cdp) 连接至此，向指定的 agent 转发 CDP 报文。"""
    if agent_id not in active_agents:
        await websocket.close(code=1008, reason="Agent not connected")
        logger.warning(f"Hub connection rejected: Agent {agent_id} not found")
        return
    
    agent_conn = active_agents[agent_id]
    agent_ws = agent_conn.ws
    await websocket.accept()
    logger.info(f"Hub connected to Agent: {agent_id}")
    
    # 无脑双工转发
    async def hub_to_agent():
        try:
            while True:
                data = await websocket.receive_text()
                await agent_ws.send_text(data)
        except WebSocketDisconnect:
            logger.debug(f"Relay hub->agent disconnected for {agent_id}")
        except Exception as e:
            logger.error(f"Relay error hub->agent for {agent_id}: {e}")

    async def agent_to_hub():
        try:
            while True:
                data = await agent_conn.hub_queue.get()
                await websocket.send_text(data)
        except WebSocketDisconnect:
            logger.debug(f"Relay agent->hub disconnected for {agent_id}")
        except Exception as e:
            logger.error(f"Relay error agent->hub for {agent_id}: {e}")

    # 并发执行双工数据流
    t1 = asyncio.create_task(hub_to_agent())
    t2 = asyncio.create_task(agent_to_hub())
    
    # 任何一端断开，另一个任务也将停止
    done, pending = await asyncio.wait(
        [t1, t2], 
        return_when=asyncio.FIRST_COMPLETED
    )
    
    for task in pending:
        task.cancel()
        
    try:
        await agent_ws.close()
    except Exception:
        pass
