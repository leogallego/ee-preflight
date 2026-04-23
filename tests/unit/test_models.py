from __future__ import annotations

from pathlib import Path

from ee_preflight.models import (
    EEDefinition,
    Finding,
    LayerResult,
    Severity,
)


class TestFinding:
    def test_finding_to_dict(self):
        finding = Finding(
            severity=Severity.ERROR,
            message="Missing package libxml2-devel",
            fix="Add 'libxml2-devel' to bindep.txt",
            source="system_deps",
        )
        result = finding.to_dict()

        assert result == {
            "severity": "error",
            "message": "Missing package libxml2-devel",
            "fix": "Add 'libxml2-devel' to bindep.txt",
            "source": "system_deps",
        }

    def test_finding_to_dict_optional_none(self):
        finding = Finding(
            severity=Severity.WARNING,
            message="Collection may be incompatible",
        )
        result = finding.to_dict()

        assert result["fix"] is None
        assert result["source"] is None
        assert result["severity"] == "warning"
        assert result["message"] == "Collection may be incompatible"


class TestLayerResult:
    def test_layer_result_has_errors_true(self):
        layer = LayerResult(
            name="system_deps",
            status="failed",
            findings=[
                Finding(severity=Severity.WARNING, message="minor issue"),
                Finding(severity=Severity.ERROR, message="critical issue"),
            ],
        )
        assert layer.has_errors is True

    def test_layer_result_has_errors_false(self):
        layer = LayerResult(
            name="prechecks",
            status="passed",
            findings=[
                Finding(severity=Severity.WARNING, message="minor issue"),
                Finding(severity=Severity.INFO, message="informational"),
            ],
        )
        assert layer.has_errors is False

    def test_layer_result_has_errors_empty(self):
        layer = LayerResult(name="galaxy", status="passed")
        assert layer.has_errors is False

    def test_layer_result_to_dict(self):
        layer = LayerResult(
            name="galaxy",
            status="passed",
            findings=[
                Finding(
                    severity=Severity.INFO,
                    message="All collections resolved",
                ),
            ],
        )
        result = layer.to_dict()

        assert result["name"] == "galaxy"
        assert result["status"] == "passed"
        assert len(result["findings"]) == 1
        assert result["findings"][0]["severity"] == "info"
        assert result["findings"][0]["message"] == "All collections resolved"


class TestEEDefinition:
    def test_ee_definition_build_args(self):
        ee = EEDefinition(
            path=Path("/fake/execution-environment.yml"),
            ee_dir=Path("/fake"),
            version=3,
            base_image="registry.redhat.io/ee-minimal-rhel9:latest",
            build_steps={
                "prepend_galaxy": [
                    "ADD _build/configs/ansible.cfg /etc/ansible/ansible.cfg",
                    "ARG AH_TOKEN",
                    "ENV ANSIBLE_GALAXY_SERVER_AUTOMATION_HUB_TOKEN=$AH_TOKEN",
                ],
                "prepend_base": [
                    "ARG CUSTOM_VAR=default_value",
                    "RUN echo hello",
                ],
            },
        )
        args = ee.build_args

        assert "AH_TOKEN" in args
        assert "CUSTOM_VAR" in args
        assert len(args) == 2

    def test_ee_definition_build_args_empty(self):
        ee = EEDefinition(
            path=Path("/fake/execution-environment.yml"),
            ee_dir=Path("/fake"),
            version=3,
            base_image="registry.redhat.io/ee-minimal-rhel9:latest",
            build_steps={
                "prepend_base": [
                    "RUN echo hello",
                    "ENV FOO=bar",
                ],
            },
        )
        args = ee.build_args

        assert args == []
