import React, { useState } from 'react';
import { StyleSheet, View, Text, TextInput, Button, ScrollView, SafeAreaView } from 'react-native';
import { useTelemetryStreamer } from '@/hooks/useTelemetryStreamer';

export default function HomeScreen() {
  const [serverUrl, setServerUrl] = useState('http://172.20.10.2:8000/telemetry');
  const { isStreaming, latestPacket, statusMessage, startStreaming, stopStreaming } = useTelemetryStreamer(serverUrl);

  return (
    <SafeAreaView style={styles.container}>
      <ScrollView contentContainerStyle={styles.scrollContent}>
        <Text style={styles.header}>Telemetry Client</Text>
        
        <View style={styles.inputContainer}>
          <Text style={styles.label}>Backend Server URL:</Text>
          <TextInput
            style={styles.input}
            value={serverUrl}
            onChangeText={setServerUrl}
            placeholder="http://172.20.10.2:8000/telemetry"
            autoCapitalize="none"
            autoCorrect={false}
          />
        </View>

        <View style={styles.buttonContainer}>
          <Button 
            title={isStreaming ? "Streaming Active" : "Start Streaming"} 
            onPress={startStreaming} 
            disabled={isStreaming} 
          />
          <View style={{ height: 10 }} />
          <Button 
            title="Stop Streaming" 
            onPress={stopStreaming} 
            disabled={!isStreaming} 
            color="red"
          />
        </View>

        <View style={styles.statusContainer}>
          <Text style={styles.statusLabel}>Status:</Text>
          <Text style={styles.statusText}>{statusMessage}</Text>
        </View>

        <View style={styles.packetContainer}>
          <Text style={styles.packetLabel}>Latest Packet:</Text>
          <View style={styles.packetBox}>
            <Text style={styles.packetText}>
              {latestPacket ? JSON.stringify(latestPacket, null, 2) : 'No data yet'}
            </Text>
          </View>
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#fff',
  },
  scrollContent: {
    padding: 20,
  },
  header: {
    fontSize: 24,
    fontWeight: 'bold',
    marginBottom: 20,
    textAlign: 'center',
  },
  inputContainer: {
    marginBottom: 20,
  },
  label: {
    fontSize: 16,
    marginBottom: 5,
    fontWeight: '500',
  },
  input: {
    borderWidth: 1,
    borderColor: '#ccc',
    borderRadius: 5,
    padding: 10,
    fontSize: 16,
  },
  buttonContainer: {
    marginBottom: 20,
  },
  statusContainer: {
    marginBottom: 20,
    padding: 10,
    backgroundColor: '#f0f0f0',
    borderRadius: 5,
  },
  statusLabel: {
    fontWeight: 'bold',
    marginBottom: 5,
  },
  statusText: {
    fontSize: 16,
    color: '#333',
  },
  packetContainer: {
    flex: 1,
  },
  packetLabel: {
    fontWeight: 'bold',
    marginBottom: 5,
  },
  packetBox: {
    backgroundColor: '#1e1e1e',
    padding: 10,
    borderRadius: 5,
    minHeight: 200,
  },
  packetText: {
    color: '#00ff00',
    fontFamily: 'monospace',
    fontSize: 12,
  },
});
