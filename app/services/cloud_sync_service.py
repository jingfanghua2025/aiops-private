import logging
import requests
import json
import hmac
import hashlib
import base64
from datetime import datetime
from email.utils import formatdate
from urllib.parse import urlparse
from typing import List, Dict

logger = logging.getLogger(__name__)

class CloudSyncService:
    """
    云厂商/堡垒机主机同步服务
    """
    
    def sync_hosts(self, source: str, params: Dict) -> List[Dict]:
        if source == 'tencent':
            return self._sync_tencent(params)
        elif source == 'huawei':
            return self._sync_huawei(params)
        elif source == 'aliyun':
            return self._sync_aliyun(params)
        elif source == 'jdcloud':
            return self._sync_jdcloud(params)
        elif source == 'ctyun':
            return self._sync_ctyun(params)
        elif source == 'jumpserver':
            return self._sync_jumpserver(params)
        elif source == 'spug':
            return self._sync_spug(params)
        elif source == 'teleport':
            return self._sync_teleport(params)
        else:
            raise ValueError(f"不支持的来源: {source}")

    def _sync_tencent(self, params: Dict) -> List[Dict]:
        ak = params.get('access_key')
        sk = params.get('secret_key')
        region = params.get('region', 'ap-guangzhou')
        try:
            from tencentcloud.common import credential
            from tencentcloud.common.profile.client_profile import ClientProfile
            from tencentcloud.common.profile.http_profile import HttpProfile
            from tencentcloud.cvm.v20170312 import cvm_client, models
        except ImportError:
            raise ImportError("请在服务器执行: pip install tencentcloud-sdk-python")

        try:
            cred = credential.Credential(ak, sk)
            httpProfile = HttpProfile()
            httpProfile.endpoint = "cvm.tencentcloudapi.com"
            clientProfile = ClientProfile()
            clientProfile.httpProfile = httpProfile
            client = cvm_client.CvmClient(cred, region, clientProfile)
            req = models.DescribeInstancesRequest()
            resp = client.DescribeInstances(req)
            hosts = []
            for inst in resp.InstanceSet:
                ip = inst.PublicIpAddresses[0] if inst.PublicIpAddresses else inst.PrivateIpAddresses[0]
                hosts.append({ "name": inst.InstanceName, "ip": ip, "port": 22, "username": "root", "source": "tencent", "region": region, "instance_id": inst.InstanceId })
            return hosts
        except Exception as e:
            logger.error(f"Tencent Cloud Sync Error: {e}")
            raise Exception(f"腾讯云同步失败: {str(e)}")

    def _sync_aliyun(self, params: Dict) -> List[Dict]:
        """阿里云 ECS 同步"""
        ak = params.get('access_key')
        sk = params.get('secret_key')
        region = params.get('region', 'cn-hangzhou')
        
        try:
            from aliyunsdkcore.client import AcsClient
            from aliyunsdkecs.request.v20140526.DescribeInstancesRequest import DescribeInstancesRequest
        except ImportError:
            raise ImportError("请在服务器执行: pip install aliyun-python-sdk-core aliyun-python-sdk-ecs")

        try:
            client = AcsClient(ak, sk, region)
            request = DescribeInstancesRequest()
            request.set_PageSize(50)
            
            response = client.do_action_with_exception(request)
            data = json.loads(str(response, encoding='utf-8'))
            
            hosts = []
            if 'Instances' in data and 'Instance' in data['Instances']:
                for inst in data['Instances']['Instance']:
                    pub_ips = inst.get('PublicIpAddress', {}).get('IpAddress', [])
                    priv_ips = inst.get('VpcAttributes', {}).get('PrivateIpAddress', {}).get('IpAddress', [])
                    ip = pub_ips[0] if pub_ips else (priv_ips[0] if priv_ips else None)
                    
                    if ip:
                        hosts.append({
                            "name": inst.get('InstanceName'),
                            "ip": ip,
                            "port": 22,
                            "username": "root", 
                            "source": "aliyun",
                            "region": region,
                            "instance_id": inst.get('InstanceId')
                        })
            return hosts
        except Exception as e:
            logger.error(f"Aliyun Sync Error: {e}")
            raise Exception(f"阿里云同步失败: {str(e)}")

    def _sync_huawei(self, params: Dict) -> List[Dict]:
        ak = params.get('access_key')
        sk = params.get('secret_key')
        region = params.get('region', 'cn-north-4')
        try:
            from huaweicloudsdkcore.auth.credentials import BasicCredentials
            from huaweicloudsdkecs.v2 import EcsClient, ListServersDetailsRequest
            from huaweicloudsdkcore.http.http_config import HttpConfig
        except ImportError:
            raise ImportError("请在服务器执行: pip install huaweicloud-sdk-core huaweicloud-sdk-ecs")

        try:
            credentials = BasicCredentials(ak, sk)
            config = HttpConfig.get_default_config()
            client = EcsClient.new_builder().with_credentials(credentials).with_region(None).with_http_config(config).build()
            client.endpoint = f"https://ecs.{region}.myhuaweicloud.com"
            request = ListServersDetailsRequest()
            response = client.list_servers_details(request)
            hosts = []
            for server in response.servers:
                ip = "unknown"
                for k, v in server.addresses.items():
                    for addr in v:
                        if addr.get('OS-EXT-IPS:type') == 'floating': ip = addr['addr']; break
                    if ip != "unknown": break
                if ip == "unknown" and server.addresses: ip = list(server.addresses.values())[0][0]['addr']
                hosts.append({ "name": server.name, "ip": ip, "port": 22, "username": "root", "source": "huawei", "region": region, "instance_id": server.id })
            return hosts
        except Exception as e:
            logger.error(f"Huawei Cloud Sync Error: {e}")
            raise Exception(f"华为云同步失败: {str(e)}")

    def _sync_jdcloud(self, params: Dict) -> List[Dict]:
        ak = params.get('access_key')
        sk = params.get('secret_key')
        region = params.get('region', 'cn-north-1')
        try:
            from jdcloud_sdk.core.credential import Credential
            from jdcloud_sdk.core.config import Config
            from jdcloud_sdk.core.const import SCHEME_HTTPS
            from jdcloud_sdk.services.vm.client.VmClient import VmClient
            from jdcloud_sdk.services.vm.apis.DescribeInstancesRequest import DescribeInstancesRequest
        except ImportError:
            raise ImportError("请在服务器执行: pip install jdcloud_sdk")

        try:
            credential = Credential(ak, sk)
            config = Config(region, SCHEME_HTTPS)
            client = VmClient(credential, config)
            req = DescribeInstancesRequest(regionId=region)
            resp = client.describeInstances(req)
            hosts = []
            if resp and resp.result and resp.result.instances:
                for inst in resp.result.instances:
                    ip = inst.privateIpAddress 
                    if inst.elasticIpAddress: ip = inst.elasticIpAddress
                    hosts.append({ "name": inst.instanceName, "ip": ip, "port": 22, "username": "root", "source": "jdcloud", "region": region, "instance_id": inst.instanceId })
            return hosts
        except Exception as e:
            logger.error(f"JDCloud Sync Error: {e}")
            raise Exception(f"京东云同步失败: {str(e)}")

    def _sync_ctyun(self, params: Dict) -> List[Dict]:
        raise NotImplementedError("天翼云同步暂未实现，请等待后续版本更新")

    def _sync_spug(self, params: Dict) -> List[Dict]:
        url = params.get('url')
        token = params.get('access_key') 
        if not url or not token:
            raise ValueError("Spug 需要 URL 和 API Token (在 access_key 字段填入)")
        api_url = f"{url.rstrip('/')}/api/host/"
        headers = { "X-Token": token, "Content-Type": "application/json", "User-Agent": "AIOps-Sync-Client" }
        try:
            resp = requests.get(api_url, headers=headers, timeout=10, verify=False)
            if resp.status_code != 200: raise Exception(f"API Error {resp.status_code}: {resp.text}")
            data = resp.json()
            if data.get('error'): raise Exception(f"Spug Error: {data['error']}")
            hosts = []
            assets = data.get('data', [])
            for asset in assets:
                hosts.append({ "name": asset.get('name') or asset.get('hostname'), "ip": asset.get('hostname') or asset.get('ip'), "port": int(asset.get('port', 22)), "username": asset.get('username', 'root'), "source": "spug", "instance_id": str(asset.get('id')) })
            return hosts
        except Exception as e:
            logger.error(f"Spug Sync Error: {e}")
            raise Exception(f"Spug 同步失败: {str(e)}")

    def _sync_jumpserver(self, params: Dict) -> List[Dict]:
        url = params.get('url')
        token = params.get('access_key') 
        secret = params.get('secret_key')
        if not url or not token: raise ValueError("Jumpserver 需要 URL 和 Token/AccessKey")
        api_url = f"{url.rstrip('/')}/api/v1/assets/assets/"
        logger.info(f"Jumpserver Sync: URL={api_url}, AK={token[:5]}..., HasSecret={bool(secret)}")
        headers = { "Content-Type": "application/json", "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36" }

        def try_request(auth_headers, strategy_name):
            req_headers = headers.copy()
            req_headers.update(auth_headers)
            try:
                resp = requests.get(api_url, headers=req_headers, timeout=10, verify=False)
                if resp.status_code == 200: return resp, None
                else: return resp, f"{strategy_name} Failed: {resp.status_code} {resp.text[:100]}"
            except Exception as e: return None, str(e)

        success_resp = None
        last_error = ""

        if secret:
            try:
                date = formatdate(usegmt=True)
                path = urlparse(api_url).path
                if not path: path = '/'
                string_to_sign = f"GET\n{path}\n{date}"
                signature = base64.b64encode(hmac.new(secret.encode('utf-8'), string_to_sign.encode('utf-8'), hashlib.sha256).digest()).decode()
                v2_headers = {"Date": date, "Authorization": f"Sign {token}:{signature}", "X-Jms-Org": "00000000-0000-0000-0000-000000000002"}
                resp, err = try_request(v2_headers, "v2-Sign")
                if resp: success_resp = resp
                else: last_error = err; logger.warning(f"Jumpserver v2 Auth failed: {err}")
            except Exception as e: logger.error(f"v2 Auth Generation Error: {e}")

            if not success_resp and "401" in str(last_error):
                try:
                    date = formatdate(usegmt=True)
                    path = urlparse(api_url).path
                    if not path: path = '/'
                    sign_string = f"(request-target): get {path}\ndate: {date}"
                    signature = base64.b64encode(hmac.new(secret.encode('utf-8'), sign_string.encode('utf-8'), hashlib.sha256).digest()).decode()
                    v3_headers = {"Date": date, "Authorization": f'Signature keyId="{token}",algorithm="hmac-sha256",headers="(request-target) date",signature="{signature}"', "X-Jms-Org": "00000000-0000-0000-0000-000000000002"}
                    resp, err = try_request(v3_headers, "v3-Signature")
                    if resp: success_resp = resp
                    else: last_error = err; logger.warning(f"Jumpserver v3 Auth failed: {err}")
                except Exception as e: logger.error(f"v3 Auth Generation Error: {e}")
        else:
            resp, err = try_request({"Authorization": f"Token {token}"}, "Token")
            if resp: success_resp = resp
            else: last_error = err

        if not success_resp: raise Exception(f"Jumpserver 同步失败: {last_error}")

        try:
            data = success_resp.json()
            if isinstance(data, dict) and 'results' in data: assets = data['results']
            elif isinstance(data, list): assets = data
            else: assets = []
            hosts = []
            for asset in assets:
                platform = asset.get('platform', '').lower()
                if 'win' in platform: continue
                ip = asset.get('ip') or asset.get('address')
                if not ip: continue
                hosts.append({ "name": asset.get('hostname'), "ip": ip, "port": asset.get('port', 22), "username": "root", "source": "jumpserver", "instance_id": asset.get('id') })
            return hosts
        except Exception as e:
            logger.error(f"Jumpserver Response Parse Error: {e}")
            raise Exception(f"Jumpserver 响应解析失败: {str(e)}")

    def _sync_teleport(self, params: Dict) -> List[Dict]:
        raise NotImplementedError("Teleport 同步暂未实现")
