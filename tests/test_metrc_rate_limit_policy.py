from __future__ import annotations

from services.metrc_client import MetrcTransport
from services.metrc_rate_limit_policy import bounded_retry_after, install_metrc_rate_limit_policy


class _Response:
    def __init__(self, status_code: int, payload=None, headers=None):
        self.status_code=status_code
        self._payload=[] if payload is None else payload
        self.headers=headers or {}
    def json(self):
        return self._payload


def test_retry_after_policy_respects_provider_delay_with_bounded_ceiling():
    assert bounded_retry_after("30")==30.0
    assert bounded_retry_after("90")==30.0
    assert bounded_retry_after("0")==0.0
    assert bounded_retry_after("invalid") is None


def test_shared_metrc_transport_honors_installed_retry_after_without_real_sleep():
    install_metrc_rate_limit_policy()
    sleeps=[]
    responses=iter((
        _Response(429,headers={"Retry-After":"30"}),
        _Response(200,payload=[{"Id":1}]),
    ))
    result=MetrcTransport(
        state="MA",environment="sandbox",integrator_api_key="integrator-secret",user_api_key="user-secret",
        max_attempts=2,request_get=lambda *args,**kwargs:next(responses),sleeper=sleeps.append,
    ).get("packages/v2/active",{"licenseNumber":"MP281234"})
    assert result["ok"] is True
    assert result["attempts"]==2
    assert sleeps==[30.0]
    assert "integrator-secret" not in repr(result)
    assert "user-secret" not in repr(result)
