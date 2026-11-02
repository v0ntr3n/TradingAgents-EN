#!/usr/bin/env python3
"""
Redis Connection and performance test scripts
"""

import redis
import time
import statistics
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import json

class RedisPerformanceTester:
    """Redis Performance tester"""
    
    def __init__(self, host=None, port=None, password=None, db=None):
        # Get configuration from environment variables, use defaults if none
        self.host = host or os.getenv('REDIS_HOST', 'localhost')
        self.port = port or int(os.getenv('REDIS_PORT', 6379))
        self.password = password or os.getenv('REDIS_PASSWORD')
        self.db = db or int(os.getenv('REDIS_DATABASE', 0))
        self.redis_client = None
        
    def connect(self):
        """Connect to Redis"""
        try:
            self.redis_client = redis.Redis(
                host=self.host,
                port=self.port,
                password=self.password,
                db=self.db,
                decode_responses=True,
                socket_connect_timeout=5,
                socket_timeout=5
            )
            # test connection
            self.redis_client.ping()
            print(f"✅ Successfully connected to Redis: {self.host}:{self.port}")
            return True
        except redis.ConnectionError as e:
            print(f"❌ Redis Connection failed: {e}")
            return False
        except Exception as e:
            print(f"❌ Connection error: {e}")
            return False
    
    def test_connection_latency(self, iterations=100):
        """Test connection latency"""
        print(f"\n🔍 Test connection latency ({iterations} ping test)...")
        
        latencies = []
        failed_count = 0
        
        for i in range(iterations):
            try:
                start_time = time.time()
                self.redis_client.ping()
                end_time = time.time()
                latency = (end_time - start_time) * 1000  # Convert to milliseconds
                latencies.append(latency)
                
                if (i + 1) % 20 == 0:
                    print(f"  Progress: {i + 1}/{iterations}")
                    
            except Exception as e:
                failed_count += 1
                print(f"  No.{i+1}ping failed: {e}")
        
        if latencies:
            avg_latency = statistics.mean(latencies)
            min_latency = min(latencies)
            max_latency = max(latencies)
            median_latency = statistics.median(latencies)
            
            print(f"\n📊 Connection latency statistics:")
            print(f"  average delay: {avg_latency:.2f} ms")
            print(f"  minimum delay: {min_latency:.2f} ms")
            print(f"  maximum delay: {max_latency:.2f} ms")
            print(f"  median latency: {median_latency:.2f} ms")
            print(f"  Number of failures: {failed_count}/{iterations}")
            
            return {
                'avg_latency': avg_latency,
                'min_latency': min_latency,
                'max_latency': max_latency,
                'median_latency': median_latency,
                'failed_count': failed_count,
                'success_rate': (iterations - failed_count) / iterations * 100
            }
        else:
            print("❌ All ping tests fail")
            return None
    
    def test_throughput(self, operations=1000, operation_type='set'):
        """Test throughput"""
        print(f"\n🚀 test{operation_type.upper()}Operation throughput ({operations} operations)...")
        
        start_time = time.time()
        failed_count = 0
        
        try:
            if operation_type == 'set':
                for i in range(operations):
                    try:
                        self.redis_client.set(f"test_key_{i}", f"test_value_{i}")
                    except Exception:
                        failed_count += 1
                        
            elif operation_type == 'get':
                # Set up some test data first
                for i in range(min(100, operations)):
                    self.redis_client.set(f"test_key_{i}", f"test_value_{i}")
                
                for i in range(operations):
                    try:
                        self.redis_client.get(f"test_key_{i % 100}")
                    except Exception:
                        failed_count += 1
                        
            elif operation_type == 'ping':
                for i in range(operations):
                    try:
                        self.redis_client.ping()
                    except Exception:
                        failed_count += 1
            
            end_time = time.time()
            duration = end_time - start_time
            successful_ops = operations - failed_count
            throughput = successful_ops / duration if duration > 0 else 0
            
            print(f"\n📈 {operation_type.upper()}Operation throughput statistics:")
            print(f"  total number of operations: {operations}")
            print(f"  successful operation: {successful_ops}")
            print(f"  failed operation: {failed_count}")
            print(f"  Total time spent: {duration:.2f} seconds")
            print(f"  Throughput: {throughput:.2f} operations/second")
            print(f"  average per operation: {(duration/successful_ops)*1000:.2f} ms")
            
            return {
                'operation_type': operation_type,
                'total_operations': operations,
                'successful_operations': successful_ops,
                'failed_operations': failed_count,
                'duration': duration,
                'throughput': throughput,
                'avg_operation_time': (duration/successful_ops)*1000 if successful_ops > 0 else 0
            }
            
        except Exception as e:
            print(f"❌ Throughput test failed: {e}")
            return None
    
    def test_concurrent_connections(self, num_threads=10, operations_per_thread=100):
        """Test concurrent connection performance"""
        print(f"\n🔀 Test concurrent connection performance ({num_threads} thread, per thread {operations_per_thread} Operation)...")
        
        def worker_task(thread_id):
            """Worker thread tasks"""
            try:
                # Each thread creates its own Redis connection
                client = redis.Redis(
                    host=self.host,
                    port=self.port,
                    password=self.password,
                    db=self.db,
                    decode_responses=True
                )
                
                start_time = time.time()
                failed_count = 0
                
                for i in range(operations_per_thread):
                    try:
                        client.set(f"thread_{thread_id}_key_{i}", f"value_{i}")
                        client.get(f"thread_{thread_id}_key_{i}")
                    except Exception:
                        failed_count += 1
                
                end_time = time.time()
                duration = end_time - start_time
                successful_ops = (operations_per_thread * 2) - failed_count  # set + get
                
                return {
                    'thread_id': thread_id,
                    'duration': duration,
                    'successful_operations': successful_ops,
                    'failed_operations': failed_count,
                    'throughput': successful_ops / duration if duration > 0 else 0
                }
                
            except Exception as e:
                return {
                    'thread_id': thread_id,
                    'error': str(e),
                    'successful_operations': 0,
                    'failed_operations': operations_per_thread * 2
                }
        
        # Perform concurrent testing
        start_time = time.time()
        results = []
        
        with ThreadPoolExecutor(max_workers=num_threads) as executor:
            futures = [executor.submit(worker_task, i) for i in range(num_threads)]
            
            for future in as_completed(futures):
                result = future.result()
                results.append(result)
                print(f"  thread {result['thread_id']} Complete")
        
        end_time = time.time()
        total_duration = end_time - start_time
        
        # Statistical results
        total_successful = sum(r['successful_operations'] for r in results)
        total_failed = sum(r['failed_operations'] for r in results)
        total_operations = total_successful + total_failed
        overall_throughput = total_successful / total_duration if total_duration > 0 else 0
        
        print(f"\n📊 Concurrency test statistics:")
        print(f"  Total number of threads: {num_threads}")
        print(f"  total number of operations: {total_operations}")
        print(f"  successful operation: {total_successful}")
        print(f"  failed operation: {total_failed}")
        print(f"  Total time spent: {total_duration:.2f} seconds")
        print(f"  overall throughput: {overall_throughput:.2f} operations/second")
        print(f"  success rate: {(total_successful/total_operations)*100:.1f}%")
        
        return {
            'num_threads': num_threads,
            'total_operations': total_operations,
            'successful_operations': total_successful,
            'failed_operations': total_failed,
            'total_duration': total_duration,
            'overall_throughput': overall_throughput,
            'success_rate': (total_successful/total_operations)*100,
            'thread_results': results
        }
    
    def test_memory_usage(self):
        """Test Redis memory usage"""
        print(f"\n💾 Redis Memory usage:")
        
        try:
            info = self.redis_client.info('memory')
            
            used_memory = info.get('used_memory', 0)
            used_memory_human = info.get('used_memory_human', 'N/A')
            used_memory_peak = info.get('used_memory_peak', 0)
            used_memory_peak_human = info.get('used_memory_peak_human', 'N/A')
            
            print(f"  Current memory usage: {used_memory_human} ({used_memory} bytes)")
            print(f"  Peak memory usage: {used_memory_peak_human} ({used_memory_peak} bytes)")
            
            return {
                'used_memory': used_memory,
                'used_memory_human': used_memory_human,
                'used_memory_peak': used_memory_peak,
                'used_memory_peak_human': used_memory_peak_human
            }
            
        except Exception as e:
            print(f"❌ Failed to obtain memory information: {e}")
            return None
    
    def run_full_test(self):
        """Run a complete performance test"""
        print("🧪 Start Redis performance test...")
        
        if not self.connect():
            return None
        
        results = {}
        
        # 1. Connection latency test
        results['latency'] = self.test_connection_latency(100)
        
        # 2. Throughput test
        results['set_throughput'] = self.test_throughput(1000, 'set')
        results['get_throughput'] = self.test_throughput(1000, 'get')
        results['ping_throughput'] = self.test_throughput(1000, 'ping')
        
        # 3. Concurrency testing
        results['concurrent'] = self.test_concurrent_connections(10, 50)
        
        # 4. memory usage
        results['memory'] = self.test_memory_usage()
        
        # Clean test data
        try:
            self.redis_client.flushdb()
            print("\n🧹 Cleaning test data completed")
        except Exception as e:
            print(f"⚠️  Cleaning test data failed: {e}")
        
        return results

def main():
    """main function"""
    parser = argparse.ArgumentParser(description="Redis Performance testing tools")
    parser.add_argument("--host", default="localhost", help="Redis host address")
    parser.add_argument("--port", type=int, default=6379, help="Redis port")
    parser.add_argument("--password", help="Redis Password")
    parser.add_argument("--db", type=int, default=0, help="Redis database number")
    parser.add_argument("--test", choices=['latency', 'throughput', 'concurrent', 'memory', 'all'], 
                       default='all', help="Test type")
    parser.add_argument("--output", help="result output file(JSON Format)")
    
    args = parser.parse_args()
    
    tester = RedisPerformanceTester(args.host, args.port, args.password, args.db)
    
    if args.test == 'all':
        results = tester.run_full_test()
    else:
        if not tester.connect():
            return
            
        if args.test == 'latency':
            results = {'latency': tester.test_connection_latency()}
        elif args.test == 'throughput':
            results = {
                'set_throughput': tester.test_throughput(1000, 'set'),
                'get_throughput': tester.test_throughput(1000, 'get')
            }
        elif args.test == 'concurrent':
            results = {'concurrent': tester.test_concurrent_connections()}
        elif args.test == 'memory':
            results = {'memory': tester.test_memory_usage()}
    
    # Save results
    if args.output and results:
        try:
            with open(args.output, 'w', encoding='utf-8') as f:
                json.dump(results, f, indent=2, ensure_ascii=False)
            print(f"\n💾 Test results have been saved to: {args.output}")
        except Exception as e:
            print(f"❌ Failed to save results: {e}")
    
    print("\n✅ Redis Performance test completed!")

if __name__ == "__main__":
    main()
