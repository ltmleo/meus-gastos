from .santander import SantanderImporter
from .nubank import NubankImporter

# New providers implement parse(content, extension, reference_month).
IMPORTERS = {'santander': SantanderImporter(), 'nubank': NubankImporter()}
