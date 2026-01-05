import os
import json
import logging

logger = logging.getLogger(__name__)


def _mask_phone(phone: str) -> str:
    phone = (phone or '').strip()
    if len(phone) >= 7:
        return phone[:3] + '****' + phone[-4:]
    return phone


class AliyunSmsService:
    """阿里云短信服务（Dysmsapi 2017-05-25）。

    通过 .env 配置：
    - ALIYUN_ACCESS_KEY_ID
    - ALIYUN_ACCESS_KEY_SECRET
    - ALIYUN_SMS_SIGN_NAME
    - ALIYUN_SMS_TEMPLATE_CODE
    可选：
    - ALIYUN_SMS_ENDPOINT (默认 dysmsapi.aliyuncs.com)
    """

    def __init__(self):
        self.access_key_id = os.getenv('ALIYUN_ACCESS_KEY_ID', '').strip()
        self.access_key_secret = os.getenv('ALIYUN_ACCESS_KEY_SECRET', '').strip()
        self.sign_name = os.getenv('ALIYUN_SMS_SIGN_NAME', '').strip()
        self.template_code = os.getenv('ALIYUN_SMS_TEMPLATE_CODE', '').strip()
        self.endpoint = os.getenv('ALIYUN_SMS_ENDPOINT', 'dysmsapi.aliyuncs.com').strip()

    def is_configured(self) -> bool:
        return all([self.access_key_id, self.access_key_secret, self.sign_name, self.template_code])

    def send_verification_code(self, phone: str, code: str) -> None:
        """发送验证码短信。

        模板变量：{ "code": "xxxxxx" }
        """
        if not self.is_configured():
            raise RuntimeError('阿里云短信未配置：请在 .env 配置 ALIYUN_ACCESS_KEY_ID/ALIYUN_ACCESS_KEY_SECRET/ALIYUN_SMS_SIGN_NAME/ALIYUN_SMS_TEMPLATE_CODE')

        # 延迟 import：避免未安装依赖时影响其他功能启动
        try:
            from alibabacloud_dysmsapi20170525.client import Client as Dysmsapi20170525Client
            from alibabacloud_tea_openapi import models as open_api_models
            from alibabacloud_dysmsapi20170525 import models as dysmsapi_models
        except Exception as exc:
            raise RuntimeError('缺少阿里云短信依赖，请安装 alibabacloud-dysmsapi20170525') from exc

        config = open_api_models.Config(
            access_key_id=self.access_key_id,
            access_key_secret=self.access_key_secret,
            endpoint=self.endpoint,
        )
        client = Dysmsapi20170525Client(config)

        req = dysmsapi_models.SendSmsRequest(
            phone_numbers=phone,
            sign_name=self.sign_name,
            template_code=self.template_code,
            template_param=json.dumps({'code': str(code)}, ensure_ascii=False),
        )

        resp = client.send_sms(req)

        # 阿里云返回 Code=OK 表示成功
        body = getattr(resp, 'body', None)
        r_code = getattr(body, 'code', None)
        r_msg = getattr(body, 'message', None)
        r_biz = getattr(body, 'biz_id', None)
        if str(r_code).upper() != 'OK':
            raise RuntimeError(f'阿里云短信发送失败: code={r_code}, message={r_msg}')

        logger.info('阿里云短信已发送 biz_id=%s phone=%s', r_biz, _mask_phone(phone))


aliyun_sms_service = AliyunSmsService()
