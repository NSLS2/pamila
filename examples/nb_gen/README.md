- Need `jupytext` to generate notebooks from the Python scripts files in this
folder.

- As an example, use the following command to generate a notebook:

`$ jupytext --to notebook 00_setup_machine_config.py -o ../00_setup_machine_config.ipynb`

- Or, if you want to conver all notebooks, just run the Python scrip:

`$ python auto_gen_notebooks.py`
