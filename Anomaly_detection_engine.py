import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from statsmodels.tsa.statespace.sarimax import SARIMAX
from sklearn.preprocessing import StandardScaler
from tensorflow.keras.models import Sequential
from tensorflow.keras.layers import LSTM, Dense, Dropout

class APIAnomalyDetector:
    def __init__(self, environment_type="cloud"):
        """
        Initialize the anomaly detector with environment-specific parameters
        
        Args:
            environment_type: The type of environment (on-prem, cloud, hybrid)
        """
        self.environment_type = environment_type
        self.models = {}
        self.sensitivity = self._get_environment_sensitivity()
        
    def _get_environment_sensitivity(self):
        """Get environment-specific sensitivity parameters."""
        sensitivity_map = {
            "on-prem": {"response_time": 1.0, "error_rate": 1.2},
            "cloud": {"response_time": 1.3, "error_rate": 1.0},
            "hybrid": {"response_time": 1.5, "error_rate": 1.1}
        }
        return sensitivity_map.get(self.environment_type, {"response_time": 1.0, "error_rate": 1.0})
    
    def train_statistical_model(self, api_id, time_series_data):
        """Train a SARIMA model for response time forecasting."""
        # Convert to pandas Series if not already
        if not isinstance(time_series_data, pd.Series):
            time_series_data = pd.Series(time_series_data)
            
        # Fit SARIMA model
        model = SARIMAX(
            time_series_data,
            order=(1, 1, 1),
            seasonal_order=(1, 1, 1, 24)  # 24-hour seasonality
        )
        results = model.fit(disp=False)
        self.models[f"{api_id}_sarima"] = results
        return results
    
    def train_isolation_forest(self, api_id, features):
        """Train an Isolation Forest model for multivariate anomaly detection."""
        scaler = StandardScaler()
        scaled_features = scaler.fit_transform(features)
        
        model = IsolationForest(
            contamination=0.01,  # Expect 1% anomalies
            random_state=42
        )
        model.fit(scaled_features)
        
        self.models[f"{api_id}_isolation_forest"] = {
            "model": model,
            "scaler": scaler
        }
        return model
    
    def train_lstm_model(self, api_id, time_series_data, sequence_length=10):
        """Train an LSTM model for complex pattern detection."""
        # Prepare sequences
        sequences = []
        targets = []
        
        for i in range(len(time_series_data) - sequence_length):
            sequences.append(time_series_data[i:i+sequence_length])
            targets.append(time_series_data[i+sequence_length])
            
        X = np.array(sequences).reshape(-1, sequence_length, 1)
        y = np.array(targets)
        
        # Create and train LSTM model
        model = Sequential([
            LSTM(50, return_sequences=True, input_shape=(sequence_length, 1)),
            Dropout(0.2),
            LSTM(50),
            Dropout(0.2),
            Dense(1)
        ])
        
        model.compile(optimizer='adam', loss='mse')
        model.fit(X, y, epochs=50, batch_size=32, verbose=0)
        
        self.models[f"{api_id}_lstm"] = {
            "model": model,
            "sequence_length": sequence_length
        }
        return model
    
    def detect_response_time_anomalies(self, api_id, new_data, threshold_multiplier=None):
        """Detect response time anomalies using the trained model."""
        if threshold_multiplier is None:
            threshold_multiplier = self.sensitivity["response_time"]
            
        # Get the SARIMA model
        model_key = f"{api_id}_sarima"
        if model_key not in self.models:
            raise ValueError(f"No trained model found for {api_id}")
            
        model = self.models[model_key]
        
        # Make one-step forecast
        forecast = model.forecast(steps=1)
        forecast_value = forecast.values[0]
        
        # Calculate dynamic threshold
        residuals = model.resid
        threshold = threshold_multiplier * np.std(residuals)
        
        # Check if actual value exceeds threshold
        actual_value = new_data[-1]
        deviation = abs(actual_value - forecast_value)
        
        is_anomaly = deviation > threshold
        
        return {
            "is_anomaly": is_anomaly,
            "actual": actual_value,
            "forecast": forecast_value,
            "deviation": deviation,
            "threshold": threshold,
            "severity": deviation / threshold if is_anomaly else 0
        }
    
    def detect_multivariate_anomalies(self, api_id, new_features):
        """Detect anomalies using isolation forest."""
        model_key = f"{api_id}_isolation_forest"
        if model_key not in self.models:
            raise ValueError(f"No trained model found for {api_id}")
            
        model_dict = self.models[model_key]
        model = model_dict["model"]
        scaler = model_dict["scaler"]
        
        # Scale the features
        scaled_features = scaler.transform(new_features)
        
        # Predict anomalies (-1 for anomalies, 1 for normal)
        predictions = model.predict(scaled_features)
        anomaly_scores = model.decision_function(scaled_features)
        
        return {
            "is_anomaly": predictions == -1,
            "anomaly_scores": anomaly_scores,
            "severity": abs(anomaly_scores)
        }

class CrossEnvironmentCorrelator:
    """Correlate anomalies across different environments."""
    
    def __init__(self):
        self.request_journeys = {}  # Store request journey graphs
        
    def register_request_journey(self, journey_id, api_sequence):
        """Register a new request journey."""
        self.request_journeys[journey_id] = api_sequence
        
    def correlate_anomalies(self, anomaly_events, time_window=300):  # 5-minute window
        """Correlate anomalies across environments within a time window."""
        # Group anomalies by time window
        time_buckets = {}
        
        for event in anomaly_events:
            timestamp = event["timestamp"]
            bucket_key = timestamp - (timestamp % time_window)
            
            if bucket_key not in time_buckets:
                time_buckets[bucket_key] = []
                
            time_buckets[bucket_key].append(event)
        
        # Analyze each time bucket for correlations
        correlated_events = []
        
        for bucket_key, events in time_buckets.items():
            if len(events) <= 1:
                continue  # Need at least 2 events to correlate
                
            # Group by request journey if possible
            journey_events = {}
            for event in events:
                journey_id = event.get("journey_id")
                if journey_id:
                    if journey_id not in journey_events:
                        journey_events[journey_id] = []
                    journey_events[journey_id].append(event)
            
            # Create correlation groups
            for journey_id, j_events in journey_events.items():
                if len(j_events) > 1:
                    correlated_events.append({
                        "correlation_id": f"corr-{bucket_key}-{journey_id}",
                        "events": j_events,
                        "correlation_type": "request_journey",
                        "journey_id": journey_id
                    })
        
        return correlated_events