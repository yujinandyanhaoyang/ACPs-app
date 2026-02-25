"""
mTLS (Mutual TLS) 配置模块

提供通用的mTLS证书加载和SSL上下文创建功能，供服务器端和客户端使用。
"""

import os
import ssl
from pathlib import Path
from typing import Tuple, Optional, Dict, Any
import logging

logger = logging.getLogger(__name__)


class MTLSConfig:
    """mTLS配置类，用于管理证书和创建SSL上下文"""

    def __init__(self, cert_dir: str, aic: str, ca_cert_name: str = "ca.crt"):
        """
        初始化mTLS配置

        Args:
            cert_dir: 证书目录路径
            aic: Agent识别码，用于定位证书文件
            ca_cert_name: CA根证书文件名，默认为"ca.crt"
        """
        self.cert_dir = Path(cert_dir)
        self.aic = aic
        self.ca_cert_name = ca_cert_name

        # 构建证书文件路径
        self.cert_file = self.cert_dir / f"{aic}.crt"
        self.key_file = self.cert_dir / f"{aic}.key"
        self.ca_cert_file = self.cert_dir / ca_cert_name

        # 验证文件存在
        self._validate_files()

    def _validate_files(self):
        """验证所有必需的证书文件是否存在"""
        missing_files = []

        if not self.cert_file.exists():
            missing_files.append(str(self.cert_file))
        if not self.key_file.exists():
            missing_files.append(str(self.key_file))
        if not self.ca_cert_file.exists():
            missing_files.append(str(self.ca_cert_file))

        if missing_files:
            raise FileNotFoundError(
                f"Missing certificate files: {', '.join(missing_files)}"
            )

        logger.info(
            f"mTLS certificates validated for AIC={self.aic}: "
            f"cert={self.cert_file}, key={self.key_file}, ca={self.ca_cert_file}"
        )

    def create_server_ssl_context(self) -> ssl.SSLContext:
        """
        创建服务器端SSL上下文，用于接受mTLS连接

        Returns:
            配置好的SSL上下文对象
        """
        ssl_context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)

        # 加载服务器证书和私钥
        ssl_context.load_cert_chain(
            certfile=str(self.cert_file), keyfile=str(self.key_file)
        )

        # 加载CA证书用于验证客户端
        ssl_context.load_verify_locations(cafile=str(self.ca_cert_file))

        # 要求客户端提供证书（双向认证）
        ssl_context.verify_mode = ssl.CERT_REQUIRED

        # 设置安全的协议版本
        ssl_context.minimum_version = ssl.TLSVersion.TLSv1_2

        logger.info(f"Server SSL context created for AIC={self.aic}")
        return ssl_context

    def create_client_ssl_context(self) -> ssl.SSLContext:
        """
        创建客户端SSL上下文，用于建立mTLS连接

        Returns:
            配置好的SSL上下文对象
        """
        ssl_context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)

        # 加载客户端证书和私钥
        ssl_context.load_cert_chain(
            certfile=str(self.cert_file), keyfile=str(self.key_file)
        )

        # 加载CA证书用于验证服务器
        ssl_context.load_verify_locations(cafile=str(self.ca_cert_file))

        # 要求验证服务器证书
        ssl_context.check_hostname = False  # 在本地测试环境中禁用主机名检查
        ssl_context.verify_mode = ssl.CERT_REQUIRED

        # 设置安全的协议版本
        ssl_context.minimum_version = ssl.TLSVersion.TLSv1_2

        logger.info(f"Client SSL context created for AIC={self.aic}")
        return ssl_context

    def get_cert_paths(self) -> Tuple[str, str, str]:
        """
        获取证书文件路径

        Returns:
            (cert_file, key_file, ca_cert_file) 的元组
        """
        return (str(self.cert_file), str(self.key_file), str(self.ca_cert_file))


def load_mtls_config_from_json(
    json_path: str, cert_dir: Optional[str] = None, ca_cert_name: str = "ca.crt"
) -> MTLSConfig:
    """
    从JSON配置文件加载mTLS配置

    Args:
        json_path: JSON配置文件路径（包含aic字段）
        cert_dir: 证书目录，如果为None则使用JSON文件同级的certs目录
        ca_cert_name: CA根证书文件名

    Returns:
        MTLSConfig对象
    """
    import json

    with open(json_path, "r", encoding="utf-8") as f:
        config = json.load(f)

    aic = config.get("aic")
    if not aic:
        raise ValueError(f"No 'aic' field found in {json_path}")

    # 如果未指定cert_dir，使用JSON文件所在目录的上级目录下的certs目录
    if cert_dir is None:
        json_dir = Path(json_path).parent
        cert_dir = json_dir.parent / "certs"

    return MTLSConfig(cert_dir=str(cert_dir), aic=aic, ca_cert_name=ca_cert_name)


def _is_truthy(value: Optional[str]) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def mtls_enabled() -> bool:
    """Return whether mTLS should be enabled for service startup.

    Controlled by env var ``AGENT_MTLS_ENABLED`` (default: disabled).
    """
    return _is_truthy(os.getenv("AGENT_MTLS_ENABLED", "false"))


def _resolve_explicit_mtls_paths(
    json_path: str,
    payload: Dict[str, Any],
    cert_dir: Optional[str] = None,
) -> Optional[Tuple[str, str, str]]:
    mtls = payload.get("mtls") if isinstance(payload, dict) else None
    if not isinstance(mtls, dict):
        return None

    cert_path = str(mtls.get("cert_path") or "").strip()
    key_path = str(mtls.get("key_path") or "").strip()
    ca_path = str(mtls.get("ca_path") or mtls.get("ca_cert_path") or "").strip()
    if not cert_path or not key_path or not ca_path:
        return None

    json_base = Path(json_path).parent.resolve()
    cert_base = Path(cert_dir).resolve() if cert_dir else None

    def _resolve_file(raw_path: str) -> Path:
        candidate = Path(raw_path)
        if candidate.is_absolute():
            return candidate

        probe_paths = []
        if cert_base is not None:
            probe_paths.append((cert_base / candidate).resolve())
            probe_paths.append((cert_base / candidate.name).resolve())
        probe_paths.append((json_base / candidate).resolve())

        for probe in probe_paths:
            if probe.exists():
                return probe
        return probe_paths[0]

    cert_file = _resolve_file(cert_path)
    key_file = _resolve_file(key_path)
    ca_file = _resolve_file(ca_path)

    for file_path in [cert_file, key_file, ca_file]:
        if not file_path.exists():
            raise FileNotFoundError(f"Missing certificate file: {file_path}")

    return str(cert_file), str(key_file), str(ca_file)


def resolve_mtls_cert_paths(
    json_path: str,
    cert_dir: Optional[str] = None,
    ca_cert_name: str = "ca.crt",
) -> Tuple[str, str, str]:
    """Resolve cert/key/CA paths from config JSON.

    Priority:
    1) explicit ``mtls.cert_path/key_path/ca_path`` fields in JSON;
    2) fallback to AIC-based naming via ``MTLSConfig``.
    """
    import json

    with open(json_path, "r", encoding="utf-8") as f:
        payload = json.load(f)

    explicit = _resolve_explicit_mtls_paths(json_path, payload, cert_dir=cert_dir)
    if explicit is not None:
        return explicit

    cfg = load_mtls_config_from_json(json_path, cert_dir=cert_dir, ca_cert_name=ca_cert_name)
    return cfg.get_cert_paths()


def load_mtls_context(
    json_path: str,
    *,
    purpose: str = "server",
    cert_dir: Optional[str] = None,
    ca_cert_name: str = "ca.crt",
) -> Optional[ssl.SSLContext]:
    """Load and return an mTLS SSLContext when enabled.

    Returns ``None`` when ``AGENT_MTLS_ENABLED`` is disabled.
    """
    if not mtls_enabled():
        logger.info("mTLS disabled via AGENT_MTLS_ENABLED=false")
        return None

    cert_file, key_file, ca_cert_file = resolve_mtls_cert_paths(
        json_path,
        cert_dir=cert_dir,
        ca_cert_name=ca_cert_name,
    )

    if str(purpose).strip().lower() == "client":
        ssl_context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)
        ssl_context.load_cert_chain(certfile=cert_file, keyfile=key_file)
        ssl_context.load_verify_locations(cafile=ca_cert_file)
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_REQUIRED
        ssl_context.minimum_version = ssl.TLSVersion.TLSv1_2
        return ssl_context

    ssl_context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
    ssl_context.load_cert_chain(certfile=cert_file, keyfile=key_file)
    ssl_context.load_verify_locations(cafile=ca_cert_file)
    ssl_context.verify_mode = ssl.CERT_REQUIRED
    ssl_context.minimum_version = ssl.TLSVersion.TLSv1_2
    return ssl_context


def build_uvicorn_ssl_kwargs(
    json_path: str,
    *,
    cert_dir: Optional[str] = None,
    ca_cert_name: str = "ca.crt",
) -> Dict[str, Any]:
    """Build uvicorn SSL keyword arguments when mTLS is enabled."""
    if not mtls_enabled():
        return {}

    cert_file, key_file, ca_cert_file = resolve_mtls_cert_paths(
        json_path,
        cert_dir=cert_dir,
        ca_cert_name=ca_cert_name,
    )
    return {
        "ssl_certfile": cert_file,
        "ssl_keyfile": key_file,
        "ssl_ca_certs": ca_cert_file,
        "ssl_cert_reqs": ssl.CERT_REQUIRED,
        "ssl_version": ssl.PROTOCOL_TLS_SERVER,
    }
