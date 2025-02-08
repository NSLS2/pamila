#!/bin/bash

# Exit immediately if a command exits
set -e

# Ensure the current directory is where this installation script is located,
# i.e., the root of the git repository, such that the pamila package can be
# installed from the local source code.
cd "$(dirname "${BASH_SOURCE[0]}")"

# Prompt user for conda environment name (default: pamila)
read -p "Enter a new conda environment name (default: pamila): " ENV_NAME
ENV_NAME=${ENV_NAME:-pamila}

# Prompt user for facility name
read -p "Enter your facility name (e.g., nsls2): " FACILITY_NAME

# Prompt user to choose between conda and mamba
read -p "Use conda or mamba? (default: conda): " PACKAGE_MANAGER
PACKAGE_MANAGER=${PACKAGE_MANAGER:-conda}

# Check if conda is properly initialized. If not, initialize it.
if ! declare -F conda >/dev/null; then
    echo "Initializing conda..."
    eval "$(conda shell.bash hook)"
    echo "Finished initializing conda."
fi

# Check if the environment already exists
if conda env list | awk '{print $1}' | grep -qx "$ENV_NAME"; then
    echo "Conda environment '$ENV_NAME' already exists. Skipping environment creation."
else
    echo "Creating conda environment '$ENV_NAME'..."
    $PACKAGE_MANAGER create -n "$ENV_NAME" python=3.11 poetry numpy=1 scipy pint pyepics caproto h5py \
        matplotlib=3.8 ipython jupyter ipympl jupytext pytest black pre-commit pydantic=2.9 \
        -c conda-forge -y
fi

# Activate the environment just to get the env. var. "${CONDA_PREFIX}"
conda activate "$ENV_NAME"

# Set up environment variable activation and deactivation scripts
ACTIVATE_SCRIPT="${CONDA_PREFIX}/etc/conda/activate.d/${ENV_NAME}_activate.sh"
DEACTIVATE_SCRIPT="${CONDA_PREFIX}/etc/conda/deactivate.d/${ENV_NAME}_deactivate.sh"

conda deactivate

mkdir -p $(dirname "$ACTIVATE_SCRIPT")
mkdir -p $(dirname "$DEACTIVATE_SCRIPT")

echo "export PAMILA_FACILITY=\"$FACILITY_NAME\"" > "$ACTIVATE_SCRIPT"
echo "unset PAMILA_FACILITY" > "$DEACTIVATE_SCRIPT"

# Reactivate the environment and make sure the environment variable is correctly set
conda activate "$ENV_NAME"

echo "PAMILA_FACILITY is set to: $PAMILA_FACILITY"

# Install additional dependencies with pip
pip install ophyd
pip install bluesky==1.13
pip install tiled[all]
pip install accelerator-toolbox

# Build the PAMILA package from the local source code.
# (Ensure build and dist directories do not exist before building)
rm -rf build dist
poetry build

# Install the built package (handle dynamic wheel name)
WHEEL_FILE=$(ls dist/pamila-*.whl | head -n 1)
pip install "$WHEEL_FILE"

# Generate example notebooks
cd examples/nb_gen
python auto_gen_notebooks.py

# Final message
echo "Installation complete. Activate the environment with: '\$ conda activate $ENV_NAME'"
