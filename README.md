# PythonZOSConnection

这个项目主要用于通过 ZOS-API 构建、设置、优化和分析 periscopic 光学系统。

## 推荐入口

- `scripts/build_periscopic.py`：命令行入口，适合分阶段运行和指定参数。
- `periscopic.py`：轻量入口，使用默认 `PeriscopicConfig` 连接当前 OpticStudio。
- `periscopic/`：当前维护的 periscopic 包，新增功能优先放这里。

示例：

```powershell
python scripts/build_periscopic.py --no-pause-after-stage
python scripts/build_periscopic.py --only-stage 3
```

`--only-stage N` 会直接在当前打开的系统上执行某一阶段，不自动加载前序文件。

## 目录结构

- `periscopic/config.py`：集中配置，包括光学参数、优化参数、输出路径、stage 控制。
- `periscopic/connection.py`：OpticStudio / ZOS-API 连接和 API 加载。
- `periscopic/lens_builder.py`：系统初始化、波长/视场/孔径设置、初始镜组和 dummy 面。
- `periscopic/solves.py`：LDE solve 工具，包括变量、固定、pickup、边际光线高度。
- `periscopic/merit.py`：Merit Function 的高层构建，如 EFFL、PMAG、TRCX/TRCY。
- `periscopic/merit_function_utils.py`：TRCX/TRCY 三环六臂等 pupil sampling 的底层工具。
- `periscopic/optimize.py`：局部优化、merit 计算、保存 `.zos`。
- `periscopic/analysis.py`：阶段后分析和监控值提取。
- `periscopic/workflow.py`：分阶段 workflow 编排。
- `scripts/`：命令行脚本。
- `test/`：实验脚本、导出和截图辅助工具。
- `outputs/`：运行输出，不作为核心源码维护。

## 兼容文件

根目录下的 `system_settings.py`、`optimization_settings.py`、`merit_function_utils.py` 是旧脚本兼容层。它们保留原函数名，但实现已经转发到 `periscopic/` 包内对应模块。新代码建议直接从 `periscopic.*` 导入。

## 当前 workflow 阶段

当前维护的 workflow 到 Stage 5 为止：

- Stage 0：建立初始系统和基础 merit，不加入 TRCX/TRCY。
- Stage 1：空气厚度设为变量，打开 EFFL 权重。
- Stage 2：关闭空气厚度，物距设为变量，打开 PMAG 权重。
- Stage 3：物距设为无穷远并固定，关闭 PMAG，打开第一片镜两个面曲率，加入三环六臂 TRCX/TRCY，空气厚度保持变量，stop 厚度 pickup 上一面空气厚度。
- Stage 4：像面前加入 dummy 面，dummy 厚度为 0 且可变，镜1厚度改为 `final_thickness`。
- Stage 5：释放 pickup 中需要优化的曲率/厚度；镜2厚度继续由 pickup 锁死不变。

更详细的包内职责见 `periscopic/README.md`。
