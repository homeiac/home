#!/bin/bash
#
# Mac Studio Setup Script
# Sets up a new Mac Studio with development tools matching the primary Mac
#
# Usage:
#   Local:  ./setup-mac-studio.sh
#   Remote: ssh 10381054@10.5.155.43 'bash -s' < setup-mac-studio.sh
#
set -e

echo "=============================================="
echo "  Mac Studio Development Environment Setup"
echo "=============================================="
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# Check if running on macOS
if [[ "$(uname)" != "Darwin" ]]; then
    log_error "This script is for macOS only"
    exit 1
fi

echo "Detected: $(sw_vers -productName) $(sw_vers -productVersion)"
echo ""

# ============================================
# PHASE 1: Homebrew Installation
# ============================================
log_info "Phase 1: Installing Homebrew..."

if ! command -v brew &> /dev/null; then
    log_info "Installing Homebrew..."
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

    # Add Homebrew to PATH for Apple Silicon
    echo 'eval "$(/opt/homebrew/bin/brew shellenv)"' >> ~/.zprofile
    eval "$(/opt/homebrew/bin/brew shellenv)"
else
    log_info "Homebrew already installed"
fi

# Update Homebrew
log_info "Updating Homebrew..."
brew update

# ============================================
# PHASE 2: Essential CLI Tools
# ============================================
log_info "Phase 2: Installing essential CLI tools..."

FORMULAS=(
    # Version control & git tools
    git
    gh
    git-lfs
    git-filter-repo
    git-secrets

    # Container & Kubernetes
    docker
    docker-compose
    docker-completion
    docker-credential-helper
    kubernetes-cli
    helm
    flux
    kustomize
    kubeconform

    # Cloud & Infrastructure
    azure-cli
    terraform

    # Languages & runtimes
    go
    node
    nvm
    python@3.12
    python@3.13
    poetry
    pipx

    # Shell & terminal
    zsh
    thefuck
    tree

    # Text processing & search
    jq
    yq
    ripgrep

    # Networking & security
    openssh
    sshpass
    nmap
    tailscale

    # Utilities
    coreutils
    dos2unix
    p7zip
    wget
    curl
)

log_info "Installing ${#FORMULAS[@]} formula packages..."
for formula in "${FORMULAS[@]}"; do
    if brew list "$formula" &>/dev/null; then
        echo "  ✓ $formula (already installed)"
    else
        echo "  → Installing $formula..."
        brew install "$formula" || log_warn "Failed to install $formula"
    fi
done

# ============================================
# PHASE 3: GUI Applications (Casks)
# ============================================
log_info "Phase 3: Installing GUI applications..."

CASKS=(
    # Terminal
    iterm2

    # Development
    visual-studio-code
    docker

    # Utilities
    rectangle
    tailscale

    # Database tools
    pgadmin4
    db-browser-for-sqlite

    # Git tools
    git-credential-manager

    # Diff/merge
    meld

    # VNC
    tigervnc-viewer
)

log_info "Installing ${#CASKS[@]} cask applications..."
for cask in "${CASKS[@]}"; do
    if brew list --cask "$cask" &>/dev/null; then
        echo "  ✓ $cask (already installed)"
    else
        echo "  → Installing $cask..."
        brew install --cask "$cask" || log_warn "Failed to install $cask"
    fi
done

# ============================================
# PHASE 4: Oh-My-Zsh
# ============================================
log_info "Phase 4: Installing Oh-My-Zsh..."

if [[ ! -d "$HOME/.oh-my-zsh" ]]; then
    log_info "Installing Oh-My-Zsh..."
    sh -c "$(curl -fsSL https://raw.githubusercontent.com/ohmyzsh/ohmyzsh/master/tools/install.sh)" "" --unattended
else
    log_info "Oh-My-Zsh already installed"
fi

# ============================================
# PHASE 5: Shell Configuration
# ============================================
log_info "Phase 5: Configuring shell..."

# Backup existing .zshrc
if [[ -f "$HOME/.zshrc" ]]; then
    cp "$HOME/.zshrc" "$HOME/.zshrc.backup.$(date +%Y%m%d%H%M%S)"
fi

cat > "$HOME/.zshrc" << 'ZSHRC'
# Path configuration
export PATH=/opt/homebrew/bin:$HOME/bin:/usr/local/bin:$PATH

# Oh-My-Zsh configuration
export ZSH="$HOME/.oh-my-zsh"
ZSH_THEME="robbyrussell"

# Plugins
plugins=(git vscode python docker kubectl)

source $ZSH/oh-my-zsh.sh

# Aliases
alias dir=ls
alias kc=kubectl
alias k=kubectl
alias python=python3

# iTerm2 shell integration
test -e "${HOME}/.iterm2_shell_integration.zsh" && source "${HOME}/.iterm2_shell_integration.zsh"

# pipx PATH
export PATH="$PATH:$HOME/.local/bin"

# NVM configuration
export NVM_DIR="$HOME/.nvm"
[ -s "/opt/homebrew/opt/nvm/nvm.sh" ] && \. "/opt/homebrew/opt/nvm/nvm.sh"
[ -s "/opt/homebrew/opt/nvm/etc/bash_completion.d/nvm" ] && \. "/opt/homebrew/opt/nvm/etc/bash_completion.d/nvm"
[ -s "$NVM_DIR/bash_completion" ] && \. "$NVM_DIR/bash_completion"

# thefuck alias
eval $(thefuck --alias)

# Docker CLI completions
fpath=($HOME/.docker/completions $fpath)
autoload -Uz compinit
compinit
ZSHRC

log_info "Shell configuration written to ~/.zshrc"

# ============================================
# PHASE 6: Node.js via NVM
# ============================================
log_info "Phase 6: Setting up Node.js via NVM..."

# Source NVM
export NVM_DIR="$HOME/.nvm"
[ -s "/opt/homebrew/opt/nvm/nvm.sh" ] && \. "/opt/homebrew/opt/nvm/nvm.sh"

if command -v nvm &> /dev/null; then
    log_info "Installing Node.js LTS..."
    nvm install --lts
    nvm use --lts
    nvm alias default node
else
    log_warn "NVM not available in current shell, will be available after restart"
fi

# ============================================
# PHASE 7: Claude Code CLI
# ============================================
log_info "Phase 7: Installing Claude Code CLI..."

# Claude Code is installed via npm
if command -v npm &> /dev/null; then
    if npm list -g @anthropic-ai/claude-code &>/dev/null; then
        log_info "Claude Code already installed"
    else
        log_info "Installing Claude Code..."
        npm install -g @anthropic-ai/claude-code
    fi
else
    log_warn "npm not available yet, install Claude Code manually after restart:"
    log_warn "  npm install -g @anthropic-ai/claude-code"
fi

# ============================================
# PHASE 8: VS Code Extensions
# ============================================
log_info "Phase 8: Installing VS Code extensions..."

VSCODE_EXTENSIONS=(
    ms-python.python
    ms-python.vscode-pylance
    ms-azuretools.vscode-docker
    hashicorp.terraform
    redhat.vscode-yaml
    esbenp.prettier-vscode
    dbaeumer.vscode-eslint
    eamodio.gitlens
    github.copilot
    ms-vscode-remote.remote-ssh
    ms-kubernetes-tools.vscode-kubernetes-tools
)

if command -v code &> /dev/null; then
    log_info "Installing VS Code extensions..."
    for ext in "${VSCODE_EXTENSIONS[@]}"; do
        echo "  → Installing $ext..."
        code --install-extension "$ext" --force 2>/dev/null || true
    done
else
    log_warn "VS Code CLI not available, install extensions manually after opening VS Code"
fi

# ============================================
# PHASE 9: Git Configuration
# ============================================
log_info "Phase 9: Configuring Git..."

read -p "Enter your Git user name (or press Enter to skip): " GIT_NAME
read -p "Enter your Git email (or press Enter to skip): " GIT_EMAIL

if [[ -n "$GIT_NAME" ]]; then
    git config --global user.name "$GIT_NAME"
fi

if [[ -n "$GIT_EMAIL" ]]; then
    git config --global user.email "$GIT_EMAIL"
fi

# Common Git settings
git config --global init.defaultBranch main
git config --global pull.rebase false
git config --global core.autocrlf input
git config --global credential.helper osxkeychain

log_info "Git configured"

# ============================================
# PHASE 10: Create development directories
# ============================================
log_info "Phase 10: Creating development directories..."

mkdir -p "$HOME/code"
mkdir -p "$HOME/bin"

log_info "Development directories created"

# ============================================
# SUMMARY
# ============================================
echo ""
echo "=============================================="
echo "  Setup Complete!"
echo "=============================================="
echo ""
log_info "Installed:"
echo "  • Homebrew package manager"
echo "  • ${#FORMULAS[@]} CLI tools (docker, kubectl, azure-cli, etc.)"
echo "  • ${#CASKS[@]} GUI apps (iTerm2, VS Code, Docker Desktop, etc.)"
echo "  • Oh-My-Zsh with plugins"
echo "  • Node.js via NVM"
echo "  • Claude Code CLI"
echo ""
log_warn "Next steps:"
echo "  1. Restart your terminal (or run: source ~/.zshrc)"
echo "  2. Open Docker Desktop and complete setup"
echo "  3. Open iTerm2 and enable shell integration (iTerm2 > Install Shell Integration)"
echo "  4. Run 'az login' to authenticate with Azure"
echo "  5. Run 'claude' to authenticate Claude Code"
echo "  6. Copy your kubeconfig and SSH keys from your old Mac"
echo ""
log_info "To copy SSH keys from your current Mac:"
echo "  scp ~/.ssh/id_* 10381054@10.5.155.43:~/.ssh/"
echo "  scp ~/.kube/config 10381054@10.5.155.43:~/.kube/config"
echo ""
