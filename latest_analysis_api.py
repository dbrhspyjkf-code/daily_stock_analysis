#!/usr/bin/env python3
"""
命令行工具 - 获取最近一次分析的所有股票结论

打印 JSON 到标准输出后退出，不启动 Web 服务。

Usage:
    .venv/bin/python3 latest_analysis_api.py
"""

import json
import sqlite3
from pathlib import Path


def _resolve_database_path() -> Path:
    env_path = Path(__file__).resolve().parent / ".env"
    if env_path.exists():
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line.startswith("DATABASE_PATH="):
                    value = line.split("=", 1)[1].strip().strip("\"'")
                    if value:
                        p = Path(value)
                        if not p.is_absolute():
                            p = Path(__file__).resolve().parent / p
                        return p.resolve()
    return Path(__file__).resolve().parent / "data" / "stock_analysis.db"


def main():
    db_path = _resolve_database_path()

    if not db_path.exists():
        result = {"error": f"数据库文件不存在: {db_path}", "items": []}
        print(json.dumps(result, ensure_ascii=False))
        return

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        cursor = conn.execute(
            "SELECT DATE(MAX(created_at)) AS latest_date FROM analysis_history"
        )
        row = cursor.fetchone()
        if not row or not row["latest_date"]:
            result = {"error": "暂无分析记录", "items": []}
            print(json.dumps(result, ensure_ascii=False))
            return

        latest_date = row["latest_date"]

        cursor = conn.execute(
            "SELECT code, raw_result, MAX(created_at) AS max_created FROM analysis_history "
            "WHERE DATE(created_at) = ? AND report_type = 'simple' "
            "GROUP BY code "
            "ORDER BY code",
            (latest_date,),
        )
        items = []
        for row in cursor.fetchall():
            raw = row["raw_result"]
            if not raw:
                continue
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                continue

            name = data.get("name") or row["code"]
            dashboard = data.get("dashboard") or {}
            core_conclusion = dashboard.get("core_conclusion") or {}
            one_sentence = core_conclusion.get("one_sentence", "")
            signal_type = core_conclusion.get("signal_type", "")

            items.append({
                "code": row["code"],
                "name": name,
                "one_sentence": one_sentence,
                "signal_type": signal_type,
                "sentiment_score": data.get("sentiment_score"),
                "analysis_summary": data.get("analysis_summary", ""),
            })

        result = {"date": latest_date, "count": len(items), "items": items}
        print(json.dumps(result, ensure_ascii=False))
    finally:
        conn.close()


if __name__ == "__main__":
    main()
