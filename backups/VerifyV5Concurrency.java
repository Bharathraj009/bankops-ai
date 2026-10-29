import java.sql.*;
import java.util.UUID;
import java.util.concurrent.*;

class VerifyV5Concurrency {
    static Connection connect() throws SQLException {
        return DriverManager.getConnection(System.getenv("VERIFY_DB_URL"), System.getenv("VERIFY_DB_USER"), System.getenv("VERIFY_DB_PASSWORD"));
    }
    static UUID create(Connection c, String scope, UUID source, UUID destination) throws SQLException {
        try (var s = c.prepareStatement("SELECT create_idempotent_transfer(?,'concurrency-probe','probe-fingerprint',?,?,10)")) {
            s.setString(1, scope); s.setObject(2, source); s.setObject(3, destination);
            try (var r = s.executeQuery()) { r.next(); return r.getObject(1, UUID.class); }
        }
    }
    public static void main(String[] args) throws Exception {
        UUID source = UUID.randomUUID(), destination = UUID.randomUUID();
        String scope = UUID.randomUUID().toString();
        try (var executor = Executors.newSingleThreadExecutor(); var first = connect()) {
            first.setAutoCommit(false);
            try {
                try (var s = first.prepareStatement("INSERT INTO accounts(id,account_number,balance) VALUES (?,?,100),(?,?,100)")) {
                    s.setObject(1, source); s.setString(2, source.toString());
                    s.setObject(3, destination); s.setString(4, destination.toString()); s.executeUpdate();
                }
                UUID transfer = create(first, scope, source, destination);
                var result = executor.submit(() -> {
                    try (var second = connect()) {
                        second.setAutoCommit(false);
                        try {
                            try (var s = second.createStatement()) { s.execute("SET LOCAL lock_timeout='1s'"); }
                            create(second, scope, source, destination);
                            throw new IllegalStateException("Concurrent duplicate bypassed the uncommitted claim");
                        } catch (SQLException error) {
                            if (!"55P03".equals(error.getSQLState()) || !error.getMessage().contains("idempotency_records")) throw error;
                            return error.getSQLState();
                        } finally { second.rollback(); }
                    }
                });
                if (!"55P03".equals(result.get(10, TimeUnit.SECONDS))) throw new IllegalStateException("Claim did not serialize duplicates");
                if (!transfer.equals(create(first, scope, source, destination))) throw new IllegalStateException("Retry did not reuse transfer");
                try (var s = first.prepareStatement("SELECT count(*) FROM transfers WHERE source_account_id=?")) {
                    s.setObject(1, source);
                    try (var r = s.executeQuery()) { r.next(); if (r.getInt(1)!=1) throw new IllegalStateException("Duplicate transfers created"); }
                }
                System.out.println("Concurrent duplicate blocked on the scoped claim; one transfer; both transactions rolled back");
            } finally { first.rollback(); }
        }
    }
}
