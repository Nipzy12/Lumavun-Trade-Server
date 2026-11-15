"""GUI executable entrypoint."""
from multiprocessing import freeze_support
from lumavun.gui import main

if __name__ == "__main__":
    freeze_support()
    main()
