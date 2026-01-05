from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
from app.api.endpoints import get_current_user, get_db
from app.models.user import User, SSHHost
from app.services.cloud_sync_service import CloudSyncService

router = APIRouter()
sync_service = CloudSyncService()

class CloudSyncSchema(BaseModel):
    source: str
    access_key: Optional[str] = None
    secret_key: Optional[str] = None
    region: Optional[str] = None
    url: Optional[str] = None # For jumpserver

@router.post("/ssh/hosts/sync")
async def sync_cloud_hosts(
    req: CloudSyncSchema, 
    user: User = Depends(get_current_user), 
    db: Session = Depends(get_db)
):
    try:
        # 1. Fetch hosts from source
        params = req.dict()
        hosts_data = sync_service.sync_hosts(req.source, params)
        
        # 2. Save to DB
        count = 0
        updated = 0
        for h_data in hosts_data:
            # Check if exists (by ip + owner_id)
            existing = db.query(SSHHost).filter(
                SSHHost.ip == h_data['ip'], 
                SSHHost.owner_id == user.id
            ).first()
            
            if existing:
                # Update info
                existing.name = h_data['name']
                existing.source = h_data['source']
                existing.region = h_data.get('region')
                existing.instance_id = h_data.get('instance_id')
                updated += 1
            else:
                new_host = SSHHost(
                    name=h_data['name'],
                    ip=h_data['ip'],
                    port=h_data['port'],
                    username=h_data['username'],
                    owner_id=user.id,
                    source=h_data['source'],
                    region=h_data.get('region'),
                    instance_id=h_data.get('instance_id'),
                    auth_type='password'
                )
                db.add(new_host)
                count += 1
        
        db.commit()
        return {
            "code": "SUCCESS",
            "message": f"同步完成: 新增 {count} 台, 更新 {updated} 台",
            "data": {"added": count, "updated": updated}
        }
        
    except ImportError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
