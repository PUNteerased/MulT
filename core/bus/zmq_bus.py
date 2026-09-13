"""
ZeroMQ asynchronous IPC message bus wrapper.
Provides ultra-low-latency PUB/SUB messaging over tcp://127.0.0.1.
"""
import asyncio
import json
from typing import Callable, Awaitable, List, Optional, Union
import zmq
import zmq.asyncio
from loguru import logger
from pydantic import BaseModel
from config.settings import ZMQ_PUB_ENDPOINT, ZMQ_SUB_ENDPOINT

class ZMQPublisher:
    """Async ZeroMQ Publisher."""
    def __init__(self, endpoint: str = ZMQ_PUB_ENDPOINT, context: Optional[zmq.asyncio.Context] = None):
        self.endpoint = endpoint
        self.context = context or zmq.asyncio.Context.instance()
        self.socket = self.context.socket(zmq.PUB)
        self.socket.setsockopt(zmq.LINGER, 0)
        self.socket.setsockopt(zmq.SNDHWM, 100000)
        self.is_bound = False

    def bind(self):
        if not self.is_bound:
            self.socket.bind(self.endpoint)
            self.is_bound = True
            logger.info(f"[ZMQ Publisher] Bound to {self.endpoint}")

    async def publish(self, topic: str, data: Union[BaseModel, dict]):
        """Publish a message under a given topic."""
        try:
            if isinstance(data, BaseModel):
                payload = data.model_dump_json()
            elif isinstance(data, dict):
                payload = json.dumps(data)
            else:
                payload = str(data)

            msg = f"{topic} {payload}"
            await self.socket.send_string(msg)
        except Exception as e:
            logger.error(f"[ZMQ Publisher] Error publishing on {topic}: {e}")

    def close(self):
        try:
            self.socket.close(linger=0)
        except Exception:
            pass


class ZMQSubscriber:
    """Async ZeroMQ Subscriber."""
    def __init__(self, endpoint: str = ZMQ_SUB_ENDPOINT, topics: Optional[List[str]] = None, context: Optional[zmq.asyncio.Context] = None):
        self.endpoint = endpoint
        self.topics = topics or [""]
        self.context = context or zmq.asyncio.Context.instance()
        self.socket = self.context.socket(zmq.SUB)
        self.socket.setsockopt(zmq.LINGER, 0)
        self.socket.setsockopt(zmq.RCVHWM, 100000)
        self.running = False

    def connect(self):
        self.socket.connect(self.endpoint)
        for topic in self.topics:
            self.socket.setsockopt_string(zmq.SUBSCRIBE, topic)
            logger.info(f"[ZMQ Subscriber] Subscribed to topic: '{topic}' at {self.endpoint}")

    async def listen(self, callback: Callable[[str, dict], Awaitable[None]]):
        """Asynchronously listen and route messages to callback(topic, payload_dict)."""
        self.running = True
        logger.info(f"[ZMQ Subscriber] Listening loop started for topics: {self.topics}")
        while self.running:
            try:
                # Use asyncio.wait_for with 200ms timeout for responsive cancellation
                msg = await asyncio.wait_for(self.socket.recv_string(), timeout=0.2)
                space_idx = msg.find(" ")
                if space_idx != -1:
                    topic = msg[:space_idx]
                    raw_payload = msg[space_idx + 1:]
                    try:
                        payload = json.loads(raw_payload)
                    except json.JSONDecodeError:
                        payload = {"raw": raw_payload}
                    await callback(topic, payload)
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break
            except Exception as e:
                if not self.running:
                    break
                logger.error(f"[ZMQ Subscriber] Error in recv loop: {e}")
                await asyncio.sleep(0.01)

    def stop(self):
        self.running = False
        try:
            self.socket.close(linger=0)
        except Exception:
            pass
