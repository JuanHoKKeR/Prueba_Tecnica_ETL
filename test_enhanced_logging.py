#!/usr/bin/env python3
"""
Script para probar el logging mejorado de errores de red
"""

import asyncio
import logging
from src.etl.extract import DataExtractor

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

async def test_enhanced_logging():
    """Probar el logging mejorado"""
    
    print("🔍 Probando logging mejorado de errores de red...")
    
    async with DataExtractor() as extractor:
        # Probar obtención de datos de crímenes (más probable que falle en cloud)
        print("\n📊 Probando fetch_crime_data...")
        crime_data = await extractor.fetch_crime_data(limit=10)
        print(f"✅ Datos de crímenes: {len(crime_data)} registros")
        
        # Probar obtención de ciclorutas
        print("\n🚲 Probando fetch_bike_lanes...")
        bike_lanes = await extractor.fetch_bike_lanes()
        print(f"✅ Ciclorutas: {len(bike_lanes)} registros")
        
        # Probar obtención de estacionamientos
        print("\n🅿️ Probando fetch_bike_parking...")
        bike_parking = await extractor.fetch_bike_parking()
        print(f"✅ Estacionamientos: {len(bike_parking)} registros")
        
        # Probar obtención de localidades
        print("\n🏙️ Probando fetch_zones (localidades)...")
        localidades = await extractor.fetch_zones("localidades")
        print(f"✅ Localidades: {len(localidades)} registros")

if __name__ == "__main__":
    asyncio.run(test_enhanced_logging())
