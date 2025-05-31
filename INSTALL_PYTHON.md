# Installing Python 3.12 on Ubuntu 22.04 for Coinbase HFT System

This guide provides step-by-step instructions for installing Python 3.12 on Ubuntu 22.04 and configuring the environment for the Coinbase International Exchange HFT system.

## 1. Install Python 3.12

```bash
# Update package lists and install prerequisites
sudo apt update
sudo apt install -y software-properties-common

# Add deadsnakes PPA for Python 3.12
sudo add-apt-repository -y ppa:deadsnakes/ppa

# Install Python 3.12 and development packages
sudo apt install -y python3.12 python3.12-venv python3.12-dev

# Install pip for Python 3.12
curl -sS https://bootstrap.pypa.io/get-pip.py | sudo python3.12
```

## 2. Install System Dependencies

```bash
# Install system dependencies for scientific Python packages
sudo apt install -y build-essential libssl-dev libffi-dev python3.12-dev
sudo apt install -y libopenblas-dev liblapack-dev gfortran libatlas-base-dev
sudo apt install -y pkg-config libfreetype6-dev libpng-dev libcairo2-dev
```

## 3. Create a Virtual Environment

```bash
# Navigate to the project directory
cd ~/coinbase_hft

# Create a new virtual environment with Python 3.12
python3.12 -m venv .venv

# Activate the virtual environment
source .venv/bin/activate

# Verify Python version
python --version  # Should output Python 3.12.x
```

## 4. Install Dependencies

```bash
# Upgrade pip
pip install --upgrade pip

# Install project dependencies
pip install -r requirements.txt
```

## 5. Set PYTHONPATH

```bash
# Set PYTHONPATH to include the current directory
export PYTHONPATH=$PYTHONPATH:$(pwd)

# To make this permanent, add to your .bashrc
echo 'export PYTHONPATH=$PYTHONPATH:~/coinbase_hft' >> ~/.bashrc
source ~/.bashrc
```

## 6. Create Required Directories

```bash
# Create directories for logs, data, and models
mkdir -p log store models dashboard/data
```

## 7. Test the Setup

```bash
# Run the test setup script
python test_setup.py

# Run the system in test mode
python run_hft_system.py --test --dashboard
```

## Troubleshooting

If you encounter import errors despite packages being installed:

1. **Check Python Path**:
   ```bash
   python -c "import sys; print(sys.path)"
   ```

2. **Verify Package Installation**:
   ```bash
   pip list | grep asyncfix
   pip list | grep numpy
   pip list | grep pandas
   ```

3. **Reinstall Problematic Packages**:
   ```bash
   pip install -v asyncfix==1.0.1
   pip install -v numpy pandas scikit-learn
   ```

4. **Check for System vs. Virtual Environment Conflicts**:
   ```bash
   which python
   which pip
   ```

5. **If All Else Fails, Create a Fresh Environment**:
   ```bash
   deactivate
   rm -rf .venv
   python3.12 -m venv .venv
   source .venv/bin/activate
   pip install --upgrade pip
   pip install -r requirements.txt
   ```
