"""Comprehensive tests for Coral TPU initialization."""

import pytest
from pathlib import Path
from unittest import mock
import subprocess

from homelab.coral_initialization import CoralInitializer
from homelab.coral_models import (
    CoralDevice, 
    CoralMode, 
    SafetyViolationError, 
    InitializationError
)


class TestCoralInitializer:
    """Test cases for CoralInitializer class."""

    @pytest.fixture
    def initializer(self, tmp_path):
        """Create initializer with test paths."""
        coral_dir = tmp_path / "coral"
        coral_dir.mkdir()
        return CoralInitializer(coral_dir)

    @pytest.fixture
    def setup_coral_files(self, tmp_path):
        """Setup coral files for testing."""
        coral_dir = tmp_path / "coral"
        
        # Create pycoral structure
        examples_dir = coral_dir / "pycoral" / "examples"
        examples_dir.mkdir(parents=True)
        
        # Create classify_image.py
        script_file = examples_dir / "classify_image.py"
        script_file.write_text("# Mock classify_image.py script")
        
        # Create test_data directory
        test_data_dir = tmp_path / "test_data"
        test_data_dir.mkdir()
        
        # Create required test files
        model_file = test_data_dir / "mobilenet_v2_1.0_224_inat_bird_quant_edgetpu.tflite"
        model_file.write_text("mock model")
        
        labels_file = test_data_dir / "inat_bird_labels.txt"
        labels_file.write_text("mock labels")
        
        image_file = test_data_dir / "parrot.jpg"
        image_file.write_text("mock image")
        
        return {
            'coral_dir': coral_dir,
            'script_file': script_file,
            'test_data_dir': test_data_dir
        }

    def test_check_prerequisites_success(self, initializer, setup_coral_files):
        """Test successful prerequisite check."""
        initializer.coral_init_dir = setup_coral_files['coral_dir'].parent
        
        # Should not raise any exceptions
        initializer._check_prerequisites()

    def test_check_prerequisites_missing_script(self, initializer, tmp_path):
        """Test prerequisite check with missing script."""
        coral_dir = tmp_path / "coral"
        coral_dir.mkdir()
        initializer.coral_init_dir = tmp_path
        
        with pytest.raises(InitializationError, match="classify_image.py script not found"):
            initializer._check_prerequisites()

    def test_check_prerequisites_missing_model(self, initializer, setup_coral_files):
        """Test prerequisite check with missing model file."""
        # Remove model file
        model_file = setup_coral_files['test_data_dir'] / "mobilenet_v2_1.0_224_inat_bird_quant_edgetpu.tflite"
        model_file.unlink()
        
        initializer.coral_init_dir = setup_coral_files['coral_dir'].parent
        
        with pytest.raises(InitializationError, match="Model file not found"):
            initializer._check_prerequisites()

    def test_check_prerequisites_missing_labels(self, initializer, setup_coral_files):
        """Test prerequisite check with missing labels file."""
        # Remove labels file
        labels_file = setup_coral_files['test_data_dir'] / "inat_bird_labels.txt"
        labels_file.unlink()
        
        initializer.coral_init_dir = setup_coral_files['coral_dir'].parent
        
        with pytest.raises(InitializationError, match="Labels file not found"):
            initializer._check_prerequisites()

    def test_check_prerequisites_missing_image(self, initializer, setup_coral_files):
        """Test prerequisite check with missing test image."""
        # Remove test image
        image_file = setup_coral_files['test_data_dir'] / "parrot.jpg"
        image_file.unlink()
        
        initializer.coral_init_dir = setup_coral_files['coral_dir'].parent
        
        with pytest.raises(InitializationError, match="Test image not found"):
            initializer._check_prerequisites()

    def test_safety_check_google_mode_violation(self, initializer, coral_device_google):
        """Test safety check violation with Google mode device."""
        with pytest.raises(SafetyViolationError, match="SAFETY VIOLATION"):
            initializer._safety_check(coral_device_google)

    def test_safety_check_unichip_mode_pass(self, initializer, coral_device_unichip):
        """Test safety check pass with Unichip mode device."""
        # Should not raise any exceptions
        initializer._safety_check(coral_device_unichip)

    def test_safety_check_not_found_fail(self, initializer, coral_device_not_found):
        """Test safety check fail with no device found."""
        with pytest.raises(SafetyViolationError, match="No Coral device detected"):
            initializer._safety_check(coral_device_not_found)

    def test_run_initialization_script_success(self, initializer, setup_coral_files, mock_successful_init_output):
        """Test successful initialization script execution."""
        initializer.coral_init_dir = setup_coral_files['coral_dir'].parent
        
        with mock.patch('subprocess.run') as mock_run:
            mock_run.return_value.stdout = mock_successful_init_output
            mock_run.return_value.stderr = ""
            mock_run.return_value.returncode = 0
            
            result = initializer._run_initialization_script(dry_run=False)
            
            assert result is not None
            assert "13.6ms" in result.stdout
            assert "Ara macao" in result.stdout

    def test_run_initialization_script_dry_run(self, initializer, setup_coral_files):
        """Test initialization script in dry run mode."""
        initializer.coral_init_dir = setup_coral_files['coral_dir'].parent
        
        result = initializer._run_initialization_script(dry_run=True)
        
        assert result is not None
        assert result.dry_run is True

    def test_run_initialization_script_failure(self, initializer, setup_coral_files):
        """Test initialization script execution failure."""
        initializer.coral_init_dir = setup_coral_files['coral_dir'].parent
        
        with mock.patch('subprocess.run') as mock_run:
            mock_run.side_effect = subprocess.CalledProcessError(1, 'python')
            
            with pytest.raises(InitializationError, match="Initialization script failed"):
                initializer._run_initialization_script(dry_run=False)

    def test_run_initialization_script_timeout(self, initializer, setup_coral_files):
        """Test initialization script timeout."""
        initializer.coral_init_dir = setup_coral_files['coral_dir'].parent
        
        with mock.patch('subprocess.run') as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired('python', 30)
            
            with pytest.raises(InitializationError, match="Initialization script timed out"):
                initializer._run_initialization_script(dry_run=False)

    def test_initialize_coral_success(self, initializer, setup_coral_files, coral_device_unichip, mock_successful_init_output):
        """Test complete successful Coral initialization."""
        initializer.coral_init_dir = setup_coral_files['coral_dir'].parent
        
        with mock.patch('subprocess.run') as mock_run:
            mock_run.return_value.stdout = mock_successful_init_output
            mock_run.return_value.stderr = ""
            mock_run.return_value.returncode = 0
            
            result = initializer.initialize_coral(coral_device_unichip, dry_run=False)
            
            assert result is not None
            assert "Ara macao" in result.stdout

    def test_initialize_coral_safety_violation(self, initializer, coral_device_google):
        """Test Coral initialization with safety violation."""
        with pytest.raises(SafetyViolationError):
            initializer.initialize_coral(coral_device_google, dry_run=False)

    def test_initialize_coral_missing_prerequisites(self, initializer, coral_device_unichip, tmp_path):
        """Test Coral initialization with missing prerequisites."""
        # Don't setup coral files - prerequisites will be missing
        initializer.coral_init_dir = tmp_path
        
        with pytest.raises(InitializationError):
            initializer.initialize_coral(coral_device_unichip, dry_run=False)

    def test_initialize_coral_dry_run(self, initializer, setup_coral_files, coral_device_unichip):
        """Test Coral initialization in dry run mode."""
        initializer.coral_init_dir = setup_coral_files['coral_dir'].parent
        
        result = initializer.initialize_coral(coral_device_unichip, dry_run=True)
        
        assert result is not None
        assert result.dry_run is True

    def test_validate_initialization_result_success(self, initializer, mock_successful_init_output):
        """Test validation of successful initialization result."""
        result = mock.MagicMock()
        result.stdout = mock_successful_init_output
        result.returncode = 0
        
        # Should not raise any exceptions
        initializer._validate_initialization_result(result)

    def test_validate_initialization_result_no_inference_time(self, initializer):
        """Test validation failure when no inference time present."""
        result = mock.MagicMock()
        result.stdout = "No inference time found"
        result.returncode = 0
        
        with pytest.raises(InitializationError, match="Initialization validation failed"):
            initializer._validate_initialization_result(result)

    def test_validate_initialization_result_no_results_section(self, initializer):
        """Test validation failure when no results section present."""
        result = mock.MagicMock()
        result.stdout = "----INFERENCE TIME----\n13.6ms"
        result.returncode = 0
        
        with pytest.raises(InitializationError, match="Initialization validation failed"):
            initializer._validate_initialization_result(result)

    def test_validate_initialization_result_nonzero_exit(self, initializer):
        """Test validation failure with non-zero exit code."""
        result = mock.MagicMock()
        result.stdout = mock_successful_init_output
        result.returncode = 1
        
        with pytest.raises(InitializationError, match="Initialization validation failed"):
            initializer._validate_initialization_result(result)

    def test_build_script_command(self, initializer, setup_coral_files):
        """Test building the initialization script command."""
        initializer.coral_init_dir = setup_coral_files['coral_dir'].parent
        
        cmd = initializer._build_script_command()
        
        assert cmd[0] == "python3"
        assert "classify_image.py" in cmd[1]
        assert "--model" in cmd
        assert "--labels" in cmd
        assert "--input" in cmd

    def test_find_test_data_dir_success(self, initializer, setup_coral_files):
        """Test finding test_data directory."""
        initializer.coral_init_dir = setup_coral_files['coral_dir'].parent
        
        test_data_dir = initializer._find_test_data_dir()
        
        assert test_data_dir.exists()
        assert test_data_dir.name == "test_data"

    def test_find_test_data_dir_not_found(self, initializer, tmp_path):
        """Test when test_data directory not found."""
        initializer.coral_init_dir = tmp_path
        
        with pytest.raises(InitializationError, match="test_data directory not found"):
            initializer._find_test_data_dir()

    def test_coral_init_dir_property(self, initializer, tmp_path):
        """Test coral_init_dir property access."""
        new_dir = tmp_path / "new_coral"
        initializer.coral_init_dir = new_dir
        
        assert initializer.coral_init_dir == new_dir