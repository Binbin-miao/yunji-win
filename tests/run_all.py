# -*- coding: utf-8 -*-
"""一键运行全部测试

用法：
    python tests/run_all.py            # 单测 + 冒烟
    python tests/run_all.py --unit     # 仅单测
    python tests/run_all.py --smoke    # 仅 GUI 冒烟
"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable

UNIT_TESTS = [
    "test_protocol.py",
    "test_eq_coeffs.py",
    "test_eqformat.py",
    "test_fitting.py",
    "test_scan.py",
]


def run(script: str) -> bool:
    print("=" * 62)
    print(f"  {script}")
    print("=" * 62)
    env = dict(os.environ)
    env.setdefault("QT_QPA_PLATFORM", "offscreen")
    proc = subprocess.run([PY, os.path.join(HERE, script)], env=env)
    ok = proc.returncode == 0
    print(f"  -> {'通过' if ok else '失败'}\n")
    return ok


def main() -> int:
    args = set(sys.argv[1:])
    do_unit = not args or "--unit" in args
    do_smoke = not args or "--smoke" in args

    results = {}
    if do_unit:
        for t in UNIT_TESTS:
            results[t] = run(t)
    if do_smoke:
        results["smoke_gui.py"] = run("smoke_gui.py")

    print("=" * 62)
    print("  汇总")
    print("=" * 62)
    for name, ok in results.items():
        print(f"  {'[PASS]' if ok else '[FAIL]'}  {name}")
    failed = [n for n, ok in results.items() if not ok]
    print()
    if failed:
        print(f"共 {len(failed)} 项失败：{', '.join(failed)}")
        return 1
    print(f"全部 {len(results)} 项测试通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
