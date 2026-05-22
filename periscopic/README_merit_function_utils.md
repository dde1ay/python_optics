# Merit Function Utility Examples

```python
from merit_function_utils import add_ring_arm_trcx_trcy_operands

summary = add_ring_arm_trcx_trcy_operands(
    TheSystem,
    rings=4,
    arms=8,
    wavelength=1,
    radius_mode="gaussian",
    angle_mode="full",
    clear_existing=False,
    target=0.0,
    weight_scale=1.0,
)
print(summary)
```

Reproduce the default three-ring, six-arm Gaussian pupil sampling:

```python
summary = add_ring_arm_trcx_trcy_operands(
    TheSystem,
    rings=3,
    arms=6,
    wavelength=1,
    radius_mode="gaussian",
    angle_mode="zemax_symmetric",
    clear_existing=False,
    target=0.0,
    weight_scale=1.0,
)
print(summary)
```

Full three-ring, six-arm sampling:

```python
summary = add_ring_arm_trcx_trcy_operands(
    TheSystem,
    rings=3,
    arms=6,
    wavelength=1,
    radius_mode="gaussian",
    angle_mode="full",
    target=0.0,
    weight_scale=1.0,
    clear_existing=False,
)
```

Use the second wavelength:

```python
summary = add_ring_arm_trcx_trcy_operands(
    TheSystem,
    rings=3,
    arms=6,
    wavelength=2,
    radius_mode="gaussian",
    angle_mode="zemax_symmetric",
    target=0.0,
    weight_scale=1.0,
    clear_existing=False,
)
```
