---
name: mx_self_select
description: 妙想自选管理skill，基于东方财富通行证账户数据及行情底层数据构建，支持通过自然语言查询、添加、删除自选股。
version: 1.0.0
author: 东方财富妙想团队
---

# 妙想自选管理skill (mx_self_select)

通过自然语言查询或操作东方财富通行证账户下的自选股数据，接口返回JSON格式内容。

## 功能列表
- ✅ 查询我的自选股列表
- ✅ 添加指定股票到我的自选股列表
- ✅ 从我的自选股列表中删除指定股票

## 配置

- **API Key**: 通过环境变量 `MX_APIKEY` 设置（与其他妙想技能共享）
- **默认输出目录**: `/Users/leenzhou/workspace/mx_data/output/`（自动创建）
- **输出文件名前缀**: `mx_self_select_`
- **输出文件**:
  - `mx_self_select_{query}.csv` - 自选股列表 CSV 格式
  - `mx_self_select_{query}.json` - 自选股列表 JSON 格式

## References
- [本地客户端自选股读取限制](references/local-client-selfselect-limit.md)

## 前置要求
1. 获取东方财富妙想Skills页面的apikey
2. 将apikey配置到环境变量 `MX_APIKEY`（可在 `~/.hermes/.env` 中配置）
3. 确保网络可以访问 `https://mkapi2.dfcfs.com`

   > ⚠️ **安全注意事项**
   >
   > - **外部请求**: 本 Skill 会将您的查询文本发送至东方财富官方 API 域名 ( `mkapi2.dfcfs.com` ) 以获取金融数据。
   > - **凭据保护**: API Key 仅通过环境变量 `EASTMONEY_APIKEY` 在服务端或受信任的运行环境中使用，不会在前端明文暴露。


## 使用方式

### 1. 查询自选股列表
```bash
python3 scripts/mx_self_select.py query
```
或自然语言查询：
```bash
python3 scripts/mx_self_select.py "查询我的自选股列表"
```

### 2. 添加股票到自选股
```bash
python3 scripts/mx_self_select.py add "贵州茅台"
```
或自然语言：
```bash
python3 scripts/mx_self_select.py "把贵州茅台添加到我的自选股列表"
```

### 3. 删除自选股
```bash
python3 scripts/mx_self_select.py delete "贵州茅台"
```
或自然语言：
```bash
python3 scripts/mx_self_select.py "把贵州茅台从我的自选股列表删除"
```

## 接口说明
### 查询接口
- URL: `https://mkapi2.dfcfs.com/finskillshub/api/claw/self-select/get`
- 方法: POST
- Header: `apikey: {MX_APIKEY}`

### 管理接口（添加/删除）
- URL: `https://mkapi2.dfcfs.com/finskillshub/api/claw/self-select/manage`
- 方法: POST
- Header: `apikey: {MX_APIKEY}`
- Body: `{"query": "自然语言指令"}`

## 输出示例
### 查询自选股成功
```
📊 我的自选股列表
================================================================================
股票代码 | 股票名称 | 最新价(元) | 涨跌幅(%) | 涨跌额(元) | 换手率(%) | 量比
--------------------------------------------------------------------------------
600519   | 贵州茅台 | 1850.00    | +2.78%    | +50.00     | 0.35%     | 1.2
300750   | 宁德时代 | 380.00     | -1.25%    | -4.80      | 0.89%     | 0.9
================================================================================
共 2 只自选股
```

### 添加/删除成功
```
✅ 操作成功：贵州茅台已添加到自选股列表
```

## 错误处理
- 未配置apikey: 
  1. 提示设置环境变量 `MX_APIKEY`
  2. **Fallback**: 检查默认输出目录 `/Users/leenzhou/workspace/mx_data/output/` 中是否有历史查询结果文件 `mx_self_select_*.csv`，可直接读取展示
- 接口调用失败: 显示错误信息
- 数据为空: 提示用户到东方财富App查询。

## 自选股分析标准化流程
当用户需要对自选股进行多维度分析时，按照以下标准步骤执行：
1. 获取最新自选股列表：执行`python3 ~/.hermes/skills/mx-selfselect/scripts/mx_self_select.py "查询我的自选股列表"`，提取股票代码、名称、最新价、涨跌幅基础信息
2. 配套调用mx-data（eastmoney_fin_data）获取每只股票的核心分析维度数据：
   - 基本面核心支撑信号（最新财报、行业地位、业绩增速）
   - 最新交易日MACD技术信号解读
   - 最近7天主力资金流入流出趋势
   - 最近7天融资融券余额变化情况
3. 使用`templates/self_select_analysis_template.md`生成结构化分析报告，每只股票单独列出核心洞察和操作建议
4. 报告默认发送到飞书Home频道，调用`send_message`时`target`参数需使用`feishu`（禁止使用中文"飞书"避免报错）
