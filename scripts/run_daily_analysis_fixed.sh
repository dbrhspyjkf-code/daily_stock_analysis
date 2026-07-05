#!/bin/bash
set -e
echo "SETUP"
source /Users/leenzhou/.zshrc 2>/dev/null || true
echo "SOURCE DONE"

SCRIPT_DIR="/Users/leenzhou/.hermes/skills/mx-selfselect/scripts"
PROJECT_DIR="/Users/leenzhou/daily_stock_analysis"
LOG_FILE="$PROJECT_DIR/logs/daily_analysis.log"
mkdir -p "$(dirname "$LOG_FILE")"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" >> "$LOG_FILE"; }
log "========== 开始执行每日收盘分析 =========="

OUTPUT=$(cd "$SCRIPT_DIR" && python3 mx_self_select.py query 2>&1)
echo "OUTPUT_EXIT=$?"

if echo "$OUTPUT" | grep -q "股票代码"; then
    STOCK_CODES=$(echo "$OUTPUT" | grep -E '^[0-9]' | awk '{print $1}' | tr '\n' ',' | sed 's/,$//')
    echo "CODES: $STOCK_CODES"

    # 更新.env
    if grep -q "^STOCK_LIST=" "$PROJECT_DIR/.env"; then
        sed -i '' "s/^STOCK_LIST=.*/STOCK_LIST=$STOCK_CODES/" "$PROJECT_DIR/.env"
    else
        echo "STOCK_LIST=$STOCK_CODES" >> "$PROJECT_DIR/.env"
    fi

    log "开始执行分析脚本..."
    cd "$PROJECT_DIR"
    if .venv/bin/python main.py --stocks "$STOCK_CODES" 2>&1 | tee -a "$LOG_FILE"; then
        log "✅ 分析执行完成"
        echo "分析执行完成"
    else
        log "❌ 分析执行失败"
        echo "分析执行失败"
        exit 1
    fi
else
    log "❌ 获取自选股列表失败"
    log "输出: $OUTPUT"
    echo "获取自选股列表失败: $OUTPUT"
    exit 1
fi
