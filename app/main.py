"""ApplPi Unicorn: started by ApplPi OS (applpi-app.service), or on a PC with `python app\\main.py` (set PORT if 80 is
taken; it keeps its settings in a state folder in the current one)."""
import product
from base.device import run

run(product)
