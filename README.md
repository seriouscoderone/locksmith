# LockSmith
This is  the KERI Foundation open port of the LockSmith wallet

to update assets, in locksmith directory run
```bash
python ./scripts/generate_qrc.py; pyside6-rcc resources.qrc -o resources_rc.py; mv resources_rc.py ./src/locksmith;
```

To run the app:
```bash
python ./src/locksmith/main.py
```
