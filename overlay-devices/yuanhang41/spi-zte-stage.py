"""Stage the ZTE vendor spi controller + wire it into the kbuild."""
from pathlib import Path

def apply(kernel):
    kernel = Path(kernel)
    src = Path(__file__).resolve().parents[2] / 'overlay' / 'spi_zte'
    (kernel / 'drivers/spi/spi-sprd-ums9620.c').write_bytes(
        (src / 'spi-sprd-ums9620.c').read_bytes())
    mk = kernel / 'drivers/spi/Makefile'
    text = mk.read_text()
    if 'spi-sprd-ums9620' not in text:
        text += 'obj-$(CONFIG_SPI_SPRD_UMS9620) += spi-sprd-ums9620.o\n'
        mk.write_text(text, newline='\n')
    kc = kernel / 'drivers/spi/Kconfig'
    text = kc.read_text()
    if 'config SPI_SPRD_UMS9620' not in text:
        text += ('config SPI_SPRD_UMS9620\n'
                 '\ttristate "Spreadtrum UMS9620 SPI controller (ZTE vendor 5.4 port)"\n'
                 '\tdepends on SPI_MASTER && (ARCH_SPRD || COMPILE_TEST)\n'
                 '\thelp\n'
                 '\t  ZTE vendor sprd SPI controller for UMS9620 (qogirn6pro),\n'
                 '\t  staged for the 7541N touch bus spi@70000. Matches\n'
                 '\t  "sprd,ums9620-spi" ahead of the in-tree sc9860 fallback so\n'
                 '\t  the touch IC is driven by the controller code it is\n'
                 '\t  verified against.\n')
        kc.write_text(text, newline='\n')
    print('spi-sprd-ums9620 staged')

if __name__ == '__main__':
    import sys
    apply(sys.argv[1])
