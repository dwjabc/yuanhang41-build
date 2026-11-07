"""Point charger-manager at the board NTC when the stock DTB omits cm-thermal-zone.

The bootloader hands the kernel Android's device tree. Its charger-manager
node carries no cm-thermal-zone, so the module never binds a thermal zone:
every poll logs "Can not to get board temperature, return init_temp=250"
while the charge thermal regulation runs on a fake 25 C. This board's NTC
registers as "board-thmzone", and the sprd thermal driver is built-in, so
the zone exists before any module loads.
"""
from pathlib import Path


def apply(kernel):
    cm = Path(kernel) / 'drivers' / 'power' / 'supply' / 'charger-manager.c'
    s = cm.read_text(encoding='utf-8')
    if 'desc->thermal_zone = "board-thmzone"' in s:
        return  # idempotent: already staged
    old = '\tof_property_read_string(np, "cm-thermal-zone", &desc->thermal_zone);\n'
    if s.count(old) != 1:
        raise ValueError('cm-thermal-zone parse anchor changed')
    new = (old +
           '\t/* yuanhang41: the bootloader-provided DTB omits cm-thermal-zone;\n'
           '\t * the board NTC is the built-in "board-thmzone" thermal zone. */\n'
           '\tif (!desc->thermal_zone)\n'
           '\t\tdesc->thermal_zone = "board-thmzone";\n')
    cm.write_text(s.replace(old, new, 1), encoding='utf-8')


if __name__ == '__main__':
    import sys
    apply(sys.argv[1])
