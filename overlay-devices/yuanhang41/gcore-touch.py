"""Stage the Gcore GC7202 SPI touchscreen driver (ZTE 7541N panel combo).

Vendor GPL sources (ZTE kernel b50db5b6) with 5.4->6.18 API fixes applied
by fix-gcore.py. Delivered as a built-in driver: same kernel build keeps
its BTF consistent, and no rootfs autoload configuration is needed.
"""
from pathlib import Path

SRCS = ('gcore_drv_main.c', 'gcore_drv_interface.c',
        'gcore_common_interface.c', 'gcore_drv_fw_update.c')
HDRS = ('gcore_drv_common.h', 'gcore_drv_firmware.h', 'gcore_ioctl.h')

MAKEFILE = '''obj-$(CONFIG_TOUCHSCREEN_GCORE) += gcore_ts.o
gcore_ts-y := gcore_drv_main.o gcore_drv_interface.o \\
\tgcore_common_interface.o gcore_drv_fw_update.o
ccflags-$(CONFIG_TOUCHSCREEN_GCORE) += \\
\t-DCONFIG_TOUCH_DRIVER_INTERFACE_SPI \\
\t-DCONFIG_ENABLE_CHIP_TYPE_GC7202 \\
\t-DCONFIG_ENABLE_TYPE_B_PROCOTOL
'''

KCONFIG = '''config TOUCHSCREEN_GCORE
\ttristate "Gcore GC7202 SPI touchscreen (ZTE 7541N)"
\tdepends on SPI_MASTER && GPIOLIB && INPUT
\tselect INPUT_MT
\thelp
\t  Gcore GC7202 touch controller over SPI, as found in the ZTE
\t  Yuanhang 41 (7541N) lcd_gc7202_skyworth panel combo. Matches the
\t  "gcore,touchscreen" device tree compatible.
'''


def apply(kernel):
    kernel = Path(kernel)
    dest = kernel / 'drivers' / 'input' / 'touchscreen'
    dest.mkdir(parents=True, exist_ok=True)
    src = Path(__file__).resolve().parents[2] / 'overlay' / 'gcore_ts'
    for name in SRCS + HDRS:
        (dest / name).write_bytes((src / name).read_bytes())
    for name, marker, addition in (
        ('drivers/input/touchscreen/Makefile', 'CONFIG_TOUCHSCREEN_GCORE', MAKEFILE),
        ('drivers/input/touchscreen/Kconfig', 'config TOUCHSCREEN_GCORE', KCONFIG),
    ):
        path = kernel / name
        text = path.read_text()
        if marker not in text:
            path.write_text(text + '\n' + addition)
    print('gcore_ts staged: %d sources + Makefile/Kconfig' % (len(SRCS) + len(HDRS)))


if __name__ == '__main__':
    import sys
    apply(sys.argv[1])
