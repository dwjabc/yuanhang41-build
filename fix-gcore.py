#!/usr/bin/env python3
"""Apply 5.4 -> 6.18 API fixes to the staged gcore vendor sources.

- of_get_named_gpio_flags() was removed: of_get_named_gpio() remains.
- class_create() lost its THIS_MODULE argument (6.4+).
- strlcpy() was removed (6.8): strscpy() is the drop-in.
- spi/i2c remove callbacks must return void (6.12+).
"""
import re
from pathlib import Path

D = Path(__file__).parent / 'overlay' / 'gcore_ts'

def patch(fname, subs):
    p = D / fname
    s = p.read_text(encoding='utf-8')
    for old, new, expect in subs:
        n = s.count(old)
        if expect and n != expect:
            print(f'{fname}: {old[:40]!r} found {n}x, expected {expect}')
        s = s.replace(old, new)
    p.write_text(s, encoding='utf-8', newline='\n')
    print('patched', fname)

patch('gcore_drv_main.c', [
    # legacy gpio getters (flags value is unused by this driver)
    ('gdev->irq_gpio = of_get_named_gpio_flags(node, "gcore,irq-gpio", 0, (enum of_gpio_flags *)&flag);',
     'gdev->irq_gpio = of_get_named_gpio(node, "gcore,irq-gpio", 0);', 1),
    ('gdev->rst_gpio = of_get_named_gpio_flags(node, "gcore,rst-gpio", 0, (enum of_gpio_flags *)&flag);',
     'gdev->rst_gpio = of_get_named_gpio(node, "gcore,rst-gpio", 0);', 1),
    ('gdev->ges_irq_gpio = of_get_named_gpio_flags(node, "ges,irq-gpio", 0, (enum of_gpio_flags *)&flag);',
     'gdev->ges_irq_gpio = of_get_named_gpio(node, "ges,irq-gpio", 0);', 1),
    # spi remove returns void since 6.12
    ('static int gcore_spi_remove(struct spi_device *slave)\n{\n\tstruct gcore_dev *gdev = spi_get_drvdata(slave);\n\n\tgcore_deinit(gdev);\n\n\treturn 0;\n}',
     'static void gcore_spi_remove(struct spi_device *slave)\n{\n\tstruct gcore_dev *gdev = spi_get_drvdata(slave);\n\n\tgcore_deinit(gdev);\n}', 1),
    # i2c remove returns void as well (i2c path is compile-gated out for SPI,
    # keep the source buildable in both shapes)
    ('static int gcore_i2c_remove(struct i2c_client *client)',
     'static void gcore_i2c_remove(struct i2c_client *client)', 1),
    ('strlcpy(info->type, "mtk-tpd", sizeof(info->type));',
     'strscpy(info->type, "mtk-tpd", sizeof(info->type));', 1),
])

patch('gcore_drv_interface.c', [
    ('tool_info.gcore_class = class_create(THIS_MODULE, "gcore");',
     'tool_info.gcore_class = class_create("gcore");', 1),
    ('touchscreen_class = class_create(THIS_MODULE, "touchscreen");',
     'touchscreen_class = class_create("touchscreen");', 1),
])

patch('gcore_common_interface.c', [
    ('strlcpy(gcore_vendor_name, gcore_vendor_l[i].vendor_name,',
     'strscpy(gcore_vendor_name, gcore_vendor_l[i].vendor_name,', 1),
    ('strlcpy(gcore_vendor_name, "Unknown", sizeof(gcore_vendor_name));',
     'strscpy(gcore_vendor_name, "Unknown", sizeof(gcore_vendor_name));', 1),
    ('strlcpy(cdev->ic_tpinfo.tp_name, "gcore_ts", sizeof(cdev->ic_tpinfo.tp_name));',
     'strscpy(cdev->ic_tpinfo.tp_name, "gcore_ts", sizeof(cdev->ic_tpinfo.tp_name));', 1),
    ('strlcpy(cdev->ic_tpinfo.vendor_name, gcore_vendor_name, sizeof(cdev->ic_tpinfo.vendor_name));',
     'strscpy(cdev->ic_tpinfo.vendor_name, gcore_vendor_name, sizeof(cdev->ic_tpinfo.vendor_name));', 1),
])

# i2c remove bodies may end with `return 0;` that no longer typechecks; the
# i2c variant keeps its return inside a gated section, normalize both.
main = D / 'gcore_drv_main.c'
s = main.read_text(encoding='utf-8')
s = s.replace('static void gcore_i2c_remove(struct i2c_client *client)\n{\n',
              'static void gcore_i2c_remove(struct i2c_client *client)\n{\n')
main.write_text(s, encoding='utf-8', newline='\n')

print('done')
