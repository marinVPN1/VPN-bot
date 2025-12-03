import aiohttp
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from loguru import logger

class XUIClient:
    def __init__(self, base_url: str, token: str):
        self.base_url = base_url.rstrip('/')
        self.token = token
        self.session: Optional[aiohttp.ClientSession] = None

    async def __aenter__(self):
        self.session = aiohttp.ClientSession(
            headers={
                'Accept': 'application/json',
                'Authorization': f'Bearer {self.token}'
            }
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()

    async def _make_request(self, method: str, endpoint: str, data: Optional[Dict] = None) -> Dict:
        url = f"{self.base_url}{endpoint}"
        try:
            if method.upper() == 'GET':
                async with self.session.get(url) as response:
                    response.raise_for_status()
                    return await response.json()
            elif method.upper() == 'POST':
                async with self.session.post(url, json=data) as response:
                    response.raise_for_status()
                    return await response.json()
            elif method.upper() == 'PUT':
                async with self.session.put(url, json=data) as response:
                    response.raise_for_status()
                    return await response.json()
            elif method.upper() == 'DELETE':
                async with self.session.delete(url) as response:
                    response.raise_for_status()
                    return await response.json()
        except aiohttp.ClientError as e:
            logger.error(f"XUI API request failed: {e}")
            raise

    async def add_client(self, inbound_id: int, email: str, expiry_time: int, flow: str = "auto") -> Dict:
        """Add a new client to 3X-UI"""
        data = {
            "id": inbound_id,
            "settings": json.dumps({
                "clients": [{
                    "id": email,
                    "email": email,
                    "flow": flow,
                    "expiryTime": expiry_time,
                    "totalGB": 0,
                    "enable": True
                }]
            })
        }
        return await self._make_request('POST', f'/panel/api/inbounds/addClient', data)

    async def update_client(self, inbound_id: int, email: str, expiry_time: int) -> Dict:
        """Update client expiry time"""
        data = {
            "id": inbound_id,
            "settings": json.dumps({
                "clients": [{
                    "id": email,
                    "email": email,
                    "expiryTime": expiry_time,
                    "enable": True
                }]
            })
        }
        return await self._make_request('POST', f'/panel/api/inbounds/updateClient/{email}', data)

    async def del_client(self, inbound_id: int, email: str) -> Dict:
        """Delete client from 3X-UI"""
        return await self._make_request('POST', f'/panel/api/inbounds/delClient/{email}', {"id": inbound_id})

    async def get_client_traffic(self, email: str) -> Dict:
        """Get client traffic information"""
        return await self._make_request('GET', f'/panel/api/inbounds/getClientTraffics/{email}')

    async def get_inbound(self, inbound_id: int) -> Dict:
        """Get inbound information"""
        return await self._make_request('GET', f'/panel/api/inbounds/get/{inbound_id}')

    async def list_inbounds(self) -> List[Dict]:
        """List all inbounds"""
        response = await self._make_request('GET', '/panel/api/inbounds/list')
        return response.get('obj', [])

    async def get_client_subscribe(self, email: str) -> Dict:
        """Get client subscription info"""
        return await self._make_request('GET', f'/panel/api/inbounds/getClientTraffics/{email}')

    def calculate_expiry_timestamp(self, days: int) -> int:
        """Calculate expiry timestamp for given days from now"""
        expiry_date = datetime.utcnow() + timedelta(days=days)
        return int(expiry_date.timestamp() * 1000)  # 3X-UI expects milliseconds

    async def create_or_update_client(self, inbound_ids: List[int], email: str, days: int) -> Dict:
        """Create or update client in all specified inbounds"""
        expiry_time = self.calculate_expiry_timestamp(days)
        results = []

        for inbound_id in inbound_ids:
            try:
                # Try to add client first
                result = await self.add_client(inbound_id, email, expiry_time)
                results.append({"inbound_id": inbound_id, "status": "created", "result": result})
            except Exception as e:
                try:
                    # If add fails, try to update
                    result = await self.update_client(inbound_id, email, expiry_time)
                    results.append({"inbound_id": inbound_id, "status": "updated", "result": result})
                except Exception as update_e:
                    results.append({"inbound_id": inbound_id, "status": "error", "error": str(update_e)})

        return {"email": email, "expiry_time": expiry_time, "results": results}