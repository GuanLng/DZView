import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
import sys
import os

# Add the parent directory to the path so we can import main
parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, parent_dir)

from main import app

# Create a test client
client = TestClient(app)

def test_private_ip_blocked():
    """Test that private IP addresses are blocked with 403"""
    # Mock socket.gethostbyname to return a private IP
    with patch('socket.gethostbyname', return_value='192.168.1.1'):
        response = client.get("/proxy/example.local")
        assert response.status_code == 403

def test_allowed_domain_returns_200():
    """Test that allowed domains return 200"""
    # Mock the actual HTTP request to avoid external dependencies
    with patch('httpx.AsyncClient.request') as mock_request:
        # Mock response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {"content-type": "application/json"}
        mock_response.content = b'{"message": "success"}'
        
        mock_request.return_value = mock_response
        
        # Mock DNS resolution to return a public IP
        with patch('socket.gethostbyname', return_value='93.184.216.34'):  # example.com IP
            response = client.get("/proxy/example.com")
            assert response.status_code == 200

def test_upstream_timeout_returns_504():
    """Test that upstream timeout returns 504"""
    # Mock the actual HTTP request to raise a timeout exception
    with patch('httpx.AsyncClient.request') as mock_request:
        # 使用正确的超时异常类型
        from httpx import TimeoutException
        mock_request.side_effect = TimeoutException("Timeout")
        
        # Mock DNS resolution to return a public IP
        with patch('socket.gethostbyname', return_value='93.184.216.34'):
            response = client.get("/proxy/slow-website.com")
            assert response.status_code == 504

def test_dns_resolution_failure_returns_502():
    """Test that DNS resolution failure returns 502"""
    # Mock socket.gethostbyname to raise an exception
    with patch('socket.gethostbyname', side_effect=OSError("Name or service not known")):
        response = client.get("/proxy/nonexistent-domain.invalid")
        assert response.status_code == 502

def test_extract_domain_failure_returns_400():
    """Test that invalid target URLs return 400"""
    # 测试一个明显无效的URL，应该在域名提取阶段失败
    response = client.get("/proxy/")
    assert response.status_code == 400

def test_proxy_route_accepts_various_methods():
    """Test that proxy route accepts various HTTP methods"""
    # Mock the actual HTTP request
    with patch('httpx.AsyncClient.request') as mock_request:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {"content-type": "text/plain"}
        mock_response.content = b'OK'
        mock_request.return_value = mock_response
        
        # Mock DNS resolution
        with patch('socket.gethostbyname', return_value='93.184.216.34'):
            methods = ["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"]
            for method in methods:
                if method == "GET":
                    response = client.get("/proxy/example.com")
                elif method == "POST":
                    response = client.post("/proxy/example.com")
                elif method == "PUT":
                    response = client.put("/proxy/example.com")
                elif method == "DELETE":
                    response = client.delete("/proxy/example.com")
                elif method == "PATCH":
                    response = client.patch("/proxy/example.com")
                elif method == "HEAD":
                    response = client.head("/proxy/example.com")
                elif method == "OPTIONS":
                    response = client.options("/proxy/example.com")
                
                # We expect 200 for successful proxying
                assert response.status_code == 200