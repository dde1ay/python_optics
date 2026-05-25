# Periscopic Package Layout

`periscopic` 是当前维护的 periscopic 光学系统代码包。整理原则是按职责分文件，workflow 只负责编排，不把底层 ZOS-API 细节散落到阶段代码里。

## 模块职责

| 模块 | 职责 |
| --- | --- |
| `config.py` | `PeriscopicConfig`，集中管理系统参数、优化参数、输出路径和 stage 控制。 |
| `connection.py` | 查找 Zemax 安装、加载 ZOS-API、连接 standalone 或 interactive extension。 |
| `lens_builder.py` | 系统级设置和结构搭建：波长、视场、孔径、初始 LDE 表面、物距无穷远、dummy 面。 |
| `solves.py` | LDE solve 操作：固定、变量、Surface Pickup、边际光线高度，以及常用组合 solve。 |
| `merit.py` | Merit Function 高层构建：EFFL、EFLY、PMAG、监控 operand、默认 TRCX/TRCY。 |
| `merit_function_utils.py` | Merit Function 底层工具：环/臂 pupil sampling、字段坐标、TRCX/TRCY operand 批量生成。 |
| `optimize.py` | Merit 计算、Local Optimization、保存阶段文件。 |
| `analysis.py` | 阶段完成后的 RMS spot、监控 operand 和分析窗口检查。 |
| `workflow.py` | Stage 0-5 的执行顺序、暂停、只运行某一阶段、summary 输出。 |

## 推荐依赖方向

高层模块可以调用低层模块，低层模块尽量不反向依赖高层：

```text
workflow
  -> lens_builder / solves / merit / optimize / analysis
merit
  -> merit_function_utils
lens_builder
  -> solves
optimize / analysis
  -> config / merit
connection / config / merit_function_utils
  -> 尽量保持独立
```

## Stage 约定

- Stage 代码统一放在 `workflow.py`，不要把阶段顺序写进 helper。
- 与 LDE solve 相关的通用函数放在 `solves.py`。
- 与系统构建、表面插入、波长/视场/孔径有关的函数放在 `lens_builder.py`。
- 与 MFE operand 有关的高层逻辑放在 `merit.py`。
- 与 TRCX/TRCY 采样和 operand 批量生成有关的底层逻辑放在 `merit_function_utils.py`。

当前 stage：

| Stage | 说明 |
| --- | --- |
| 0 | 建立初始系统和基础 merit，不加入 TRCX/TRCY。 |
| 1 | 空气厚度为变量，EFFL 权重打开。 |
| 2 | 空气厚度固定，物距为变量，PMAG 权重打开。 |
| 3 | 物距无穷远并固定，PMAG 关闭，第一片镜两个面曲率为变量，加入三环六臂 TRCX/TRCY，空气厚度为变量，stop 厚度 pickup 上一面空气厚度。 |
| 4 | 像面前加入 dummy 面，保持前一个面距离不变；dummy 厚度为 0 且可变；镜1厚度改为 `final_thickness`。 |
| 5 | 释放 pickup 中需要优化的项；镜2厚度继续由 pickup 锁死不变。 |

## 只运行某一阶段

`PeriscopicConfig.only_stage` 或命令行 `--only-stage N` 可以直接在当前打开系统上运行某一阶段：

```powershell
python scripts/build_periscopic.py --only-stage 3
```

这不会自动加载前一个 stage 的 `.zos` 文件，也不会重建系统；调用前需要你在 OpticStudio 中打开正确状态的系统。

## 旧兼容层

根目录下保留了这些旧文件：

- `system_settings.py`
- `optimization_settings.py`
- `merit_function_utils.py`

它们现在作为兼容层转发到 `periscopic/` 包内实现。新代码优先导入包内模块。
