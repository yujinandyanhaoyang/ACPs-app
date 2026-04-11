import sys

for path in ['tests/test_uat_production.py', 'tests/test_uat_e2e.py']:
    try:
        with open(path, 'r') as f:
            content = f.read()
        
        target = """    except Exception as exc:  # noqa: BLE001 - UAT needs the exact failure root cause
        meta["status"] = "FAIL"
        meta["detail"] = str(exc)
        _record_result(
            scenario_id,
            status=meta["status"],
            detail=meta["detail"],
            duration_s=time.perf_counter() - started_at,
        )"""

        replacement = """    except Exception as exc:  # noqa: BLE001 - UAT needs the exact failure root cause
        meta["status"] = "FAIL"
        meta["detail"] = str(exc)
        _record_result(
            scenario_id,
            status=meta["status"],
            detail=meta["detail"],
            duration_s=time.perf_counter() - started_at,
        )
        raise"""
        
        if target in content:
            new_content = content.replace(target, replacement)
            with open(path, 'w') as f:
                f.write(new_content)
            print(f"Fixed {path}")
        else:
            print(f"Target not found in {path}")
    except Exception as e:
        print(f"Error with {path}: {e}")
