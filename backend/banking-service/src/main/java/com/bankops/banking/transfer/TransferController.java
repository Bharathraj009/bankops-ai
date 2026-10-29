package com.bankops.banking.transfer;

import com.bankops.banking.transfer.dto.CreateTransferRequest;
import com.bankops.banking.transfer.dto.TransferResponse;
import jakarta.validation.Valid;
import java.util.UUID;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/v1/transfers")
public class TransferController {
    private final TransferService service;
    public TransferController(TransferService service) { this.service = service; }

    @GetMapping("/{transferId}")
    public ResponseEntity<TransferResponse> get(@PathVariable UUID transferId) {
        return ResponseEntity.ok(TransferResponse.from(service.get(transferId)));
    }
    @PostMapping
    public ResponseEntity<TransferResponse> create(@RequestHeader("Idempotency-Key") String key, @Valid @RequestBody CreateTransferRequest request) {
        var result = service.create(key, request);
        return ResponseEntity.status(result.executed() ? HttpStatus.CREATED : HttpStatus.OK).body(TransferResponse.from(result.transfer()));
    }
}
