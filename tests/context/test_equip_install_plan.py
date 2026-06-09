"""Install plan: native/vendor mechanism + approval gating (pure)."""
from dummyindex.context.domains.equip import (
    Candidate,
    InstallMechanism,
    InstallPlan,
    PlannedInstall,
    PluginEntry,
    build_install_plan,
)


def _cand(name, *, trusted, is_collection=False, surfaces=()):
    return Candidate(
        plugin=PluginEntry(name=name, declared_surfaces=surfaces),
        marketplace="m",
        repo="o/r",
        trusted=trusted,
        is_collection=is_collection,
        capabilities=("docs",),
        score=2,
    )


def test_untrusted_code_plugin_requires_approval():
    plan = build_install_plan((_cand("pg", trusted=False, surfaces=("hook",)),))
    assert isinstance(plan, InstallPlan)
    pi = plan.installs[0]
    assert isinstance(pi, PlannedInstall)
    assert pi.requires_approval is True
    assert pi.mechanism == InstallMechanism.NATIVE.value
    assert pi.blast.runs_code is True


def test_trusted_code_plugin_auto_approvable():
    plan = build_install_plan((_cand("pg", trusted=True, surfaces=("hook",)),))
    assert plan.installs[0].requires_approval is False


def test_inert_untrusted_plugin_no_approval():
    plan = build_install_plan((_cand("docs", trusted=False),))
    assert plan.installs[0].requires_approval is False


def test_collection_uses_vendor_mechanism():
    plan = build_install_plan((_cand("skill-x", trusted=True, is_collection=True),))
    assert plan.installs[0].mechanism == InstallMechanism.VENDOR.value


def test_empty_candidates_empty_plan():
    assert build_install_plan(()).installs == ()
