# Drive 索引(双向链接 · 存储治理规则 3)

> Drive `Analyst-Archive/` 与 GitHub 的对应关系。**无孤儿文件**:Drive 每份文件在此有记录;每份 PDF 的 drive_file_id 回填到 analysts.jsonl 或本索引。Drive 目录保持**私有**。

## 目录树(建于 2026-08-09,folder ids)

| Drive 路径 | folder_id |
|---|---|
| Analyst-Archive/ | `1Y24Kx2C7Vjr0Tx5ycq4aLy-vJZq_dY02` |
| ├─ system-design/ | `13mhtC1j4YKOkCcV5fcxipUWtMD6gVKBQ` |
| ├─ macro/ | `1iPtokgHjrdt9wzSZgdCrwwu0qFJUmK-g` |
| ├─ strategy/ | `1RgLXY-TraqSyFJIPTnCtRFPThOJa8fwx` |
| ├─ energy/ | `1XKV0MEZW70Q3xLRNhQs4Qa-S4DmHpUDZ` |
| ├─ ai-infra/ | `1KCHofFQWZbLTVGyotnSK8MKmXJTx0mrR` |
| ├─ fx-gold/ | `1H_qs0HHX8RUZd-yBfEHGtmDrEMg8-AqK` |
| └─ backup/ | `1FVP0KWim18m447xxpCqPEMZJBfeXTTqx` |

## system-design/ 文件(GitHub 主控 ←→ Drive 归档)

| GitHub 主控(docs/) | Drive 文件 | drive_file_id |
|---|---|---|
| 工作计划书.md | 工作计划书-v1.0-归档副本.md | `1owXG9r5XkTAG71hIqdKBJhOhd-LA6V_9` |
| analyst-panel-项目计划.md | analyst-panel-项目计划-v0.2-归档副本.md | `1N_gDWuvCCGGHjBHkoCdKeAjK9R6flNiF` |
| 审计文章修订补编.md | 审计文章修订补编-R1-归档副本.md | `13vmv-AraZJXwhhsLlV4u7mYOFDzisqZZ` |
| 三组件系统宪法.md | 三组件系统宪法-归档副本.md | `12Q5voE75-fwZL-IXw3nVnEmo8dbX61hC` |
| 审计文章-…预警系统.pdf(967KB,SHA256前16=26bb06ccf7bb5881) | 指针文档(PDF在GitHub) | `17C0iB5jNUA0RhUBIjASmRfCYsOkPC7rg` |

## 说明与待办

- 归档副本为**要点版 + 指回 GitHub 主控**;内容级双供应商冗余由 **C15 年度 zip 备份**(→ backup/)实现。
- **PDF 二进制本体在 Drive 待补**:MCP 通道单次调用载不动 967KB 二进制(base64≈1.3MB)。补齐方式:① R2 service-account 管线就绪后自动上传;② 手动把 GitHub 的 PDF 拖入 system-design/ 并更新本表。
- 研报 PDF 今后入五板块子目录,命名 `日期_机构_分析师_主题.pdf`,drive_file_id 回填 analysts.jsonl(C6)。
