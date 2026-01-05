import json
import logging
import os
from typing import Dict, Optional

logger = logging.getLogger(__name__)

# 依赖库可能未安装，延迟加载并在缺失时给出友好提示
try:
    from wechatpayv3 import WeChatPay, WeChatPayType
except ImportError:
    WeChatPay = None
    WeChatPayType = None

try:
    from alipay.aop.api.AlipayClientConfig import AlipayClientConfig
    from alipay.aop.api.DefaultAlipayClient import DefaultAlipayClient
    from alipay.aop.api.request.AlipayTradePagePayRequest import AlipayTradePagePayRequest
except ImportError:
    AlipayClientConfig = None
    DefaultAlipayClient = None
    AlipayTradePagePayRequest = None


def _safe_read(path: Optional[str]) -> Optional[str]:
    """从文件读取密钥，路径不存在则返回 None。"""
    if not path:
        return None
    if not os.path.exists(path):
        logger.warning("密钥文件不存在: %s", path)
        return None
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


class PaymentService:
    """聚合微信/支付宝支付的基础封装，仅在配置齐全时启用。"""

    def __init__(self):
        self.wechat_client = None
        self.alipay_client = None
        self.wechat_enabled = False
        self.alipay_enabled = False
        self.wechat_notify_url = os.getenv("WECHAT_PAY_NOTIFY_URL")
        self.alipay_notify_url = os.getenv("ALIPAY_NOTIFY_URL")
        self.alipay_return_url = os.getenv("ALIPAY_RETURN_URL")
        self._init_wechat()
        self._init_alipay()

    # ---------------- 微信支付 ----------------
    def _init_wechat(self):
        if not WeChatPay or not WeChatPayType:
            logger.info("wechatpayv3 未安装，微信支付不可用")
            return

        mchid = os.getenv("WECHAT_MCH_ID")
        appid = os.getenv("WECHAT_APP_ID")
        cert_serial_no = os.getenv("WECHAT_MCH_CERT_SERIAL")
        private_key_path = os.getenv("WECHAT_MCH_PRIVATE_KEY_PATH")
        apiv3_key = os.getenv("WECHAT_API_V3_KEY")
        cert_dir = os.getenv("WECHAT_CERT_DIR")

        required = [mchid, appid, cert_serial_no, private_key_path, apiv3_key, self.wechat_notify_url]
        if not all(required):
            logger.info("微信支付配置不完整，已跳过初始化")
            return

        try:
            # wechatpayv3 支持传入私钥内容字符串；若给的是路径则读取内容
            private_key_content = _safe_read(private_key_path) or private_key_path
            self.wechat_client = WeChatPay(
                wechatpay_type=WeChatPayType.NATIVE,
                mchid=mchid,
                private_key=private_key_content,
                cert_serial_no=cert_serial_no,
                appid=appid,
                notify_url=self.wechat_notify_url,
                cert_dir=cert_dir,
                apiv3_key=apiv3_key,
                partner_mode=False,
            )
            self.wechat_enabled = True
        except Exception as exc:
            logger.exception("初始化微信支付失败: %s", exc)
            self.wechat_enabled = False

    def create_wechat_native(self, out_trade_no: str, amount: float, description: str) -> str:
        if not self.wechat_enabled or not self.wechat_client:
            raise ValueError("微信支付未配置或未启用")
        if amount <= 0:
            raise ValueError("充值金额必须大于 0")
        resp = self.wechat_client.pay(
            description=description,
            out_trade_no=out_trade_no,
            amount={"total": int(amount * 100)},
            attach="aiops-recharge",
        )
        # wechatpayv3 SDK 有的版本返回 dict，有的返回 (status_code, body_json)
        code_url = None
        if isinstance(resp, dict):
            code_url = resp.get("code_url")
        elif isinstance(resp, tuple) and len(resp) == 2:
            _, body = resp
            try:
                data = json.loads(body) if isinstance(body, str) else body
                if isinstance(data, dict):
                    code_url = data.get("code_url")
            except Exception:
                code_url = None
        if not code_url:
            raise ValueError("微信支付下单失败，未返回二维码链接")
        return code_url

    def parse_wechat_notify(self, headers: Dict[str, str], body: bytes) -> Dict:
        if not self.wechat_enabled or not self.wechat_client:
            raise ValueError("微信支付未配置或未启用")
        # wechatpayv3 SDK 不同版本的回调解析方法名不同：
        # - 旧/部分版本：parse_notification(headers, body)
        # - 当前环境：callback(headers, body) / decrypt_callback(headers, body)
        client = self.wechat_client
        # 1) 兼容旧实现（若存在）
        if hasattr(client, "parse_notification") and callable(getattr(client, "parse_notification")):
            return client.parse_notification(headers=headers, body=body)
        # 2) 推荐：callback() 会返回完整回调数据，并把解密后的 resource 合并进去
        if hasattr(client, "callback") and callable(getattr(client, "callback")):
            return client.callback(headers=headers, body=body)
        # 3) 兜底：decrypt_callback() 仅返回解密后的 resource（字符串/结构）
        if hasattr(client, "decrypt_callback") and callable(getattr(client, "decrypt_callback")):
            resource = client.decrypt_callback(headers=headers, body=body)
            return {"resource": resource}
        raise AttributeError("wechatpayv3 SDK 不支持回调解析方法（parse_notification/callback/decrypt_callback 均不存在）")

    # ---------------- 支付宝 ----------------
    def _init_alipay(self):
        if not DefaultAlipayClient or not AlipayTradePagePayRequest or not AlipayClientConfig:
            logger.info("alipay-sdk-python 未安装，支付宝不可用")
            return

        app_id = os.getenv("ALIPAY_APP_ID")
        private_key = _safe_read(os.getenv("ALIPAY_PRIVATE_KEY_PATH"))
        alipay_public_key = _safe_read(os.getenv("ALIPAY_PUBLIC_KEY_PATH"))
        gateway = os.getenv("ALIPAY_GATEWAY", "https://openapi.alipay.com/gateway.do")

        required = [app_id, private_key, alipay_public_key, self.alipay_notify_url]
        if not all(required):
            logger.info("支付宝配置不完整，已跳过初始化")
            return

        try:
            cfg = AlipayClientConfig()
            cfg.server_url = gateway
            cfg.app_id = app_id
            cfg.app_private_key = private_key
            cfg.alipay_public_key = alipay_public_key
            cfg.sign_type = "RSA2"
            self.alipay_client = DefaultAlipayClient(alipay_client_config=cfg, logger=logger)
            self.alipay_gateway = gateway
            self.alipay_enabled = True
        except Exception as exc:
            logger.exception("初始化支付宝失败: %s", exc)
            self.alipay_enabled = False

    def create_alipay_page(self, out_trade_no: str, amount: float, subject: str, return_url: Optional[str] = None) -> str:
        if not self.alipay_enabled or not self.alipay_client:
            raise ValueError("支付宝未配置或未启用")
        if amount <= 0:
            raise ValueError("充值金额必须大于 0")
        req = AlipayTradePagePayRequest()
        req.return_url = return_url or self.alipay_return_url
        req.notify_url = self.alipay_notify_url
        req.biz_content = {
            "out_trade_no": out_trade_no,
            "product_code": "FAST_INSTANT_TRADE_PAY",
            "total_amount": str(round(amount, 2)),
            "subject": subject
        }
        order_string = self.alipay_client.page_execute(req, http_method="GET")
        # SDK通常返回完整的跳转URL；若返回仅为查询串，补上网关前缀
        if order_string and not order_string.startswith("http"):
            order_string = f"{self.alipay_gateway}?{order_string}"
        return order_string

    def verify_alipay_notify(self, data: Dict, signature: str) -> bool:
        if not self.alipay_enabled or not self.alipay_client:
            return False
        return self.alipay_client.verify(data, signature)


payment_service = PaymentService()

